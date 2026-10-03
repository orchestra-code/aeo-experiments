/**
 * Experiment 010: run the Spyglasses recommendation judge over a task file.
 *
 * The judge is imported from the sibling spyglasses checkout (SPYGLASSES_ROOT,
 * default ../spyglasses next to this repo), so the study uses production code,
 * not a copy. The call mirrors `assessBrandMentions` in
 * packages/core/src/services/mention-assessment-judge.ts: same system prompt,
 * user message builder, schema, model, reasoning effort, maxOutputTokens and
 * retries, then the exported `postProcessMentionAssessment`. The one
 * difference is that the raw model output is kept, so the two-top-choice
 * demotion can be audited, and Langfuse telemetry is off.
 *
 * Pinning: the sha256 of the judge and its local imports is compared with
 * harness/judge_pin.json. The first run writes the pin; any later mismatch
 * stops the run. The pin also records the spyglasses commit.
 *
 * Resumable: results append to data/raw/judged_<split>.jsonl and tasks
 * already judged OK are skipped. Secrets are read from the spyglasses
 * .env.local (last OPENAI_API_KEY line wins, as dotenv does) and never printed.
 *
 * Run from the spyglasses core package so tsx and the judge's dependencies
 * resolve:
 *   cd ../spyglasses/packages/core && node_modules/.bin/tsx \
 *     ../../../aeo-experiments/experiments/010-shortlist-stability/harness/judge_runner.mts \
 *     --split explore [--limit 20] [--concurrency 8]
 */

import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
	appendFileSync,
	existsSync,
	readFileSync,
	writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXP = resolve(HERE, "..");
const REPO = resolve(EXP, "../..");
const SPY = resolve(process.env.SPYGLASSES_ROOT ?? join(REPO, "../spyglasses"));
const CORE = join(SPY, "packages/core");

const PINNED_FILES = [
	"src/services/mention-assessment-judge.ts",
	"src/config/utility-models.ts",
	"src/types/recommendation-categories.ts",
	"src/utils/brand-key.ts",
	"src/utils/brand-mention-match.ts",
	"src/utils/brand-name-canonicalization.ts",
	"src/utils/phrase-normalize.ts",
];
const PIN_PATH = join(HERE, "judge_pin.json");

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

function judgePin(): { sha256: string; files: Record<string, string>; commit: string } {
	const files: Record<string, string> = {};
	const all = createHash("sha256");
	for (const f of PINNED_FILES) {
		const body = readFileSync(join(CORE, f));
		files[f] = createHash("sha256").update(body).digest("hex");
		all.update(f).update(body);
	}
	const commit = execSync("git rev-parse HEAD", { cwd: SPY }).toString().trim();
	return { sha256: all.digest("hex"), files, commit };
}

interface Task {
	task_id: string;
	platform: string;
	question: string;
	answer: string;
	tracked: { canonical: string; aliases: string[] }[];
}

async function main() {
	const split = arg("split", "explore");
	const limit = Number(arg("limit", "0"));
	const concurrency = Number(arg("concurrency", "8"));
	const tasksPath = join(EXP, "data/raw", `tasks_${split}.jsonl`);
	const outPath = join(EXP, "data/raw", `judged_${split}.jsonl`);

	// Pin the model before anything reads the config at module load.
	process.env.UTILITY_LLM_MODEL = "openai:gpt-5.6-luna";
	process.env.UTILITY_LLM_REASONING_EFFORT = "none";
	const key = readEnvKey(join(SPY, ".env.local"), "OPENAI_API_KEY");
	if (!key) throw new Error("OPENAI_API_KEY not found in spyglasses .env.local");
	process.env.OPENAI_API_KEY = key;

	const pin = judgePin();
	if (existsSync(PIN_PATH)) {
		const saved = JSON.parse(readFileSync(PIN_PATH, "utf8"));
		if (saved.sha256 !== pin.sha256) {
			throw new Error(
				`judge code changed since the pin (${saved.sha256.slice(0, 12)} -> ${pin.sha256.slice(0, 12)}); refusing`,
			);
		}
	} else {
		writeFileSync(
			PIN_PATH,
			`${JSON.stringify({ ...pin, model: "gpt-5.6-luna", reasoningEffort: "none", pinnedAt: new Date().toISOString() }, null, 2)}\n`,
		);
	}

	const url = (f: string) => pathToFileURL(join(CORE, f)).href;
	const judge = await import(url("src/services/mention-assessment-judge.ts"));
	const models = await import(url("src/config/utility-models.ts"));
	const { normalizeBrandKey } = await import(url("src/utils/brand-key.ts"));
	const { generateObject } = createRequire(join(CORE, "package.json"))("ai");
	if (models.UTILITY_MODEL_ID !== "gpt-5.6-luna") {
		throw new Error(`utility model resolved to ${models.UTILITY_MODEL_ID}`);
	}

	const done = new Set<string>();
	if (existsSync(outPath)) {
		for (const line of readFileSync(outPath, "utf8").split("\n")) {
			if (!line.trim()) continue;
			const r = JSON.parse(line);
			if (r.ok) done.add(r.task_id);
		}
	}
	let tasks: Task[] = readFileSync(tasksPath, "utf8")
		.split("\n")
		.filter((l) => l.trim())
		.map((l) => JSON.parse(l))
		.filter((t: Task) => !done.has(t.task_id));
	if (limit > 0) tasks = tasks.slice(0, limit);
	console.log(`${done.size} already judged; ${tasks.length} to run (concurrency ${concurrency})`);

	let next = 0;
	let ok = 0;
	let failed = 0;
	async function worker() {
		while (next < tasks.length) {
			const t = tasks[next++];
			const tracked = t.tracked.map((b) => ({
				key: normalizeBrandKey(b.canonical),
				name: b.canonical,
				aliases: b.aliases,
			}));
			const canonicalByKey = Object.fromEntries(
				tracked.map((b, i) => [b.key, t.tracked[i].canonical]),
			);
			const input = {
				question: t.question,
				answer: t.answer,
				platform: t.platform,
				trackedPresent: tracked,
				vocabulary: [] as string[],
			};
			const started = Date.now();
			const record: Record<string, unknown> = {
				task_id: t.task_id,
				model: models.UTILITY_MODEL_ID,
				version: judge.MENTION_ASSESSMENT_VERSION,
				judge_sha256: pin.sha256,
			};
			try {
				if (!t.answer.trim()) {
					Object.assign(record, { ok: true, raw: { brands: [] }, brands: [], dropped: null, usage: null });
				} else {
					const result = await generateObject({
						model: models.utilityModel(),
						providerOptions: models.utilityProviderOptions(),
						system: judge.MENTION_ASSESSMENT_SYSTEM_PROMPT,
						prompt: judge.buildMentionAssessmentPrompt(input),
						schema: judge.MentionAssessmentSchema,
						maxOutputTokens: 4000,
						maxRetries: 2,
					});
					const { brands, dropped } = judge.postProcessMentionAssessment(result.object, input);
					Object.assign(record, {
						ok: true,
						raw: result.object,
						brands: brands.map((b: Record<string, unknown>) => ({
							...b,
							canonical: b.trackedKey ? canonicalByKey[b.trackedKey as string] ?? null : null,
						})),
						dropped,
						usage: result.usage,
					});
				}
				ok += 1;
			} catch (error) {
				Object.assign(record, { ok: false, error: String(error).slice(0, 500) });
				failed += 1;
			}
			record.ms = Date.now() - started;
			appendFileSync(outPath, `${JSON.stringify(record)}\n`);
			const n = ok + failed;
			if (n % 50 === 0 || n === tasks.length) {
				console.log(`${n}/${tasks.length} (ok ${ok}, failed ${failed})`);
			}
		}
	}
	await Promise.all(Array.from({ length: concurrency }, worker));
	console.log(`done: ok ${ok}, failed ${failed}`);
}

main().catch((e) => {
	console.error(String(e));
	process.exit(1);
});
