/**
 * Experiment 010: the "best for" instrument (secondary metric).
 *
 * Three subcommands over data/raw/bestfor_<split>/ files:
 *
 *   normalize  phrases.json -> norm.json. Each phrase through the platform's
 *              own `normalizePhrase` (packages/core/src/utils/phrase-normalize.ts),
 *              the grouping key "Where AI picks you" uses today.
 *   taxonomy   phrases.json -> taxonomy.json. One call per category: the
 *              category's distinct best-for phrases (with counts) go to the
 *              utility model, which proposes 4 to 8 use-case segments plus a
 *              fixed "general" segment for all-round picks.
 *   classify   phrases.json + taxonomy.json -> segments_<pass>.json. Every
 *              phrase is assigned one segment id, in batches of 60. Run twice
 *              (--pass a, --pass b) to measure test-retest agreement.
 *
 * Model: the platform's utility model (gpt-5.6-luna). Taxonomy at reasoning
 * effort medium (one call per category); classification at effort none, as
 * the production judge runs. Secrets come from the spyglasses .env.local and
 * are never printed.
 *
 * Run from the spyglasses core package (same as judge_runner.mts):
 *   cd ../spyglasses/packages/core && node_modules/.bin/tsx \
 *     ../../../aeo-experiments/experiments/010-shortlist-stability/harness/bestfor_segments.mts \
 *     <normalize|taxonomy|classify> --split explore [--pass a]
 */

import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXP = resolve(HERE, "..");
const REPO = resolve(EXP, "../..");
const SPY = resolve(process.env.SPYGLASSES_ROOT ?? join(REPO, "../spyglasses"));
const CORE = join(SPY, "packages/core");

const MIN_SEGMENTS = 4;
const MAX_SEGMENTS = 8;
const BATCH = 60;
export const GENERAL_ID = "general";

function arg(name: string, fallback: string): string {
	const i = process.argv.indexOf(`--${name}`);
	return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

function readEnvKey(path: string, key: string): string | null {
	let value: string | null = null;
	for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
		const m = line.match(new RegExp(`^\\s*${key}\\s*=\\s*(.*)$`));
		if (m) {
			const v = m[1].trim().replace(/^['"]|['"]$/g, "");
			value = v || value;
		}
	}
	return value;
}

type Phrases = Record<string, { phrase: string; count: number }[]>;
interface Segment {
	id: string;
	label: string;
	definition: string;
}
type Taxonomy = Record<string, Segment[]>;

const TAXONOMY_SYSTEM = `You organize "best for" phrases from AI product recommendations into use-case segments.

You get one product category and the distinct phrases AI answers used to say who or what a recommended brand is best for, with how often each phrase appeared. Propose between ${MIN_SEGMENTS} and ${MAX_SEGMENTS} segments that a buyer in this category would recognize as different reasons to pick a product.

Rules:
- Segments describe a buyer, a use case or a priority (for example "frequent travelers", "budget buyers", "teams already on Microsoft 365"), never a brand.
- Segments are mutually exclusive: a phrase should clearly belong to one.
- Together they cover the common phrases. Rare one-off phrases may fall outside every segment.
- Do NOT create a segment for all-round or general picks ("most people", "overall", "best all-around"): a fixed segment "general" exists for those.
- id: short snake_case. label: 2 to 5 words. definition: one sentence saying what belongs in it.`;

const CLASSIFY_SYSTEM = `You assign "best for" phrases from AI product recommendations to use-case segments.

You get a product category, its segments (id, label, definition) and a numbered list of phrases. Assign every phrase exactly one segment id:
- the segment whose definition the phrase fits best;
- "${GENERAL_ID}" for all-round or unqualified picks ("most people", "overall", "everyday use");
- "other" when the phrase fits no segment.
Return one entry per phrase number.`;

async function main() {
	const cmd = process.argv[2];
	const split = arg("split", "explore");
	const dir = join(EXP, "data/raw", `bestfor_${split}`);
	const phrases: Phrases = JSON.parse(readFileSync(join(dir, "phrases.json"), "utf8"));
	const url = (f: string) => pathToFileURL(join(CORE, f)).href;

	if (cmd === "normalize") {
		const { normalizePhrase } = await import(url("src/utils/phrase-normalize.ts"));
		const out: Record<string, string> = {};
		for (const list of Object.values(phrases)) {
			for (const { phrase } of list) out[phrase] = normalizePhrase(phrase);
		}
		writeFileSync(join(dir, "norm.json"), JSON.stringify(out, null, 1));
		console.log(`normalized ${Object.keys(out).length} phrases`);
		return;
	}

	process.env.UTILITY_LLM_MODEL = "openai:gpt-5.6-luna";
	const key = readEnvKey(join(SPY, ".env.local"), "OPENAI_API_KEY");
	if (!key) throw new Error("OPENAI_API_KEY not found in spyglasses .env.local");
	process.env.OPENAI_API_KEY = key;
	const models = await import(url("src/config/utility-models.ts"));
	const { generateObject } = createRequire(join(CORE, "package.json"))("ai");
	const { z } = createRequire(join(CORE, "package.json"))("zod");

	if (cmd === "taxonomy") {
		const schema = z.object({
			segments: z
				.array(z.object({ id: z.string(), label: z.string(), definition: z.string() }))
				.describe(`Between ${MIN_SEGMENTS} and ${MAX_SEGMENTS} segments, not counting "general".`),
		});
		const out: Taxonomy = {};
		for (const [category, list] of Object.entries(phrases)) {
			const lines = list
				.slice()
				.sort((a, b) => b.count - a.count)
				.map((p) => `${p.count}x ${p.phrase}`)
				.join("\n");
			const result = await generateObject({
				model: models.utilityModel(),
				providerOptions: models.utilityProviderOptions({ reasoningEffort: "medium" }),
				system: TAXONOMY_SYSTEM,
				prompt: `CATEGORY: ${category}\n\nPHRASES (count x phrase):\n${lines}`,
				schema,
				maxOutputTokens: 6000,
				maxRetries: 2,
			});
			const seen = new Set<string>([GENERAL_ID, "other"]);
			const segs: Segment[] = [];
			for (const s of result.object.segments as Segment[]) {
				const id = s.id.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
				if (!id || seen.has(id) || segs.length >= MAX_SEGMENTS) continue;
				seen.add(id);
				segs.push({ id, label: s.label.trim(), definition: s.definition.trim() });
			}
			segs.push({
				id: GENERAL_ID,
				label: "General or all-round",
				definition: "All-round or unqualified picks: most people, overall, everyday use.",
			});
			out[category] = segs;
			console.log(`${category}: ${segs.length} segments from ${list.length} phrases`);
		}
		writeFileSync(join(dir, "taxonomy.json"), JSON.stringify(out, null, 1));
		return;
	}

	if (cmd === "classify") {
		const pass = arg("pass", "a");
		const taxonomy: Taxonomy = JSON.parse(readFileSync(join(dir, "taxonomy.json"), "utf8"));
		const schema = z.object({
			assignments: z
				.array(z.object({ n: z.number(), segment: z.string() }))
				.describe("One entry per phrase number."),
		});
		const out: Record<string, Record<string, string>> = {};
		let calls = 0;
		for (const [category, list] of Object.entries(phrases)) {
			const segs = taxonomy[category];
			const valid = new Set([...segs.map((s) => s.id), "other"]);
			const segText = segs.map((s) => `- ${s.id}: ${s.label}. ${s.definition}`).join("\n");
			out[category] = {};
			const all = list.map((p) => p.phrase);
			for (let i = 0; i < all.length; i += BATCH) {
				const batch = all.slice(i, i + BATCH);
				const numbered = batch.map((p, j) => `${j + 1}. ${p}`).join("\n");
				const result = await generateObject({
					model: models.utilityModel(),
					providerOptions: models.utilityProviderOptions(),
					system: CLASSIFY_SYSTEM,
					prompt: `CATEGORY: ${category}\n\nSEGMENTS:\n${segText}\n\nPHRASES:\n${numbered}`,
					schema,
					maxOutputTokens: 6000,
					maxRetries: 2,
				});
				calls += 1;
				for (const a of result.object.assignments as { n: number; segment: string }[]) {
					const phrase = batch[a.n - 1];
					const seg = a.segment.trim().toLowerCase();
					if (phrase !== undefined && out[category][phrase] === undefined) {
						out[category][phrase] = valid.has(seg) ? seg : "other";
					}
				}
				for (const p of batch) out[category][p] ??= "unassigned";
			}
		}
		writeFileSync(join(dir, `segments_${pass}.json`), JSON.stringify(out, null, 1));
		console.log(`classified pass ${pass} in ${calls} calls`);
		return;
	}

	throw new Error(`unknown command ${cmd}`);
}

main().catch((e) => {
	console.error(String(e));
	process.exit(1);
});
