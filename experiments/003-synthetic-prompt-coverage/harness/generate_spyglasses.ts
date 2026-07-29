#!/usr/bin/env tsx
/**
 * Experiment 003 harness — generate a brand-anchored synthetic prompt panel
 * using the PRODUCTION Spyglasses generator (DiscoveryQueryService +
 * BrandSnapshotService), invoked outside the product with no database writes.
 *
 * The point is ecological validity: this is the exact code path a Spyglasses
 * customer's prompt panel comes from (crawl 5 pages -> BrandSnapshot ->
 * generateExpandedPrompts over the discovery frameworks). `brand_prompts` is
 * excluded: those must name the brand and are excluded from share of voice in
 * the product, so they are out of scope for a share-of-voice comparison.
 *
 * Run from the spyglasses checkout so workspace deps resolve, with the
 * react-server condition so `server-only` imports don't throw (same pattern
 * as tooling/scripts' create:user):
 *
 *   cd /Users/jcw/projects/spyglasses
 *   NODE_OPTIONS=--conditions=react-server pnpm --filter @repo/scripts exec tsx \
 *     /Users/jcw/projects/aeo-experiments/experiments/003-synthetic-prompt-coverage/harness/generate_spyglasses.ts \
 *     --domain bose.com --arm spy_a [--max-per-framework 8] [--out <dir>]
 *
 * Needs ANTHROPIC_API_KEY (generation), OPENAI_API_KEY (brand snapshot) and a
 * DATABASE_URL that merely satisfies the Prisma import chain — all read from
 * the spyglasses .env.local / .env; nothing is queried or written.
 *
 * Output: <out>/<arm>.json with the crawl page list, the full BrandSnapshot,
 * the generated queries (text + queryType + framework) and the spyglasses
 * commit hash, so the generation is reproducible/auditable. Prompt text stays
 * in data/raw (gitignored) per the research data policy.
 */

import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const SPYGLASSES = "/Users/jcw/projects/spyglasses";
const HERE = path.dirname(new URL(import.meta.url).pathname);
const DEFAULT_OUT = path.resolve(HERE, "..", "data", "raw", "generator");

// Discovery-class frameworks only (see module doc for why brand_prompts is out).
const FRAMEWORKS = [
	"original",
	"category_entry_points",
	"jobs_to_be_done",
	"buyers_journey",
	"stakeholder_perspectives",
];

function parseArgs(): { domain: string; arm: string; maxPerFramework: number; out: string } {
	const args = process.argv.slice(2);
	const get = (flag: string): string | undefined => {
		const i = args.indexOf(flag);
		return i >= 0 ? args[i + 1] : undefined;
	};
	const domain = get("--domain");
	const arm = get("--arm");
	if (!domain || !arm) {
		console.error("usage: generate_spyglasses.ts --domain <domain> --arm <spy_a|spy_b> [--max-per-framework 8] [--out <dir>]");
		process.exit(2);
	}
	return {
		domain,
		arm,
		maxPerFramework: Number(get("--max-per-framework") ?? 8),
		out: get("--out") ?? DEFAULT_OUT,
	};
}

/** Minimal dotenv: last duplicate in a file wins (dotenv convention), but
 * never override keys already present in the environment. */
function loadEnv(file: string): void {
	if (!existsSync(file)) return;
	const parsed: Record<string, string> = {};
	for (const line of readFileSync(file, "utf8").split("\n")) {
		const m = line.match(/^\s*(?:export\s+)?([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$/);
		if (!m) continue;
		let val = m[2];
		if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
			val = val.slice(1, -1);
		}
		parsed[m[1]] = val;
	}
	for (const [key, val] of Object.entries(parsed)) {
		if (!(key in process.env)) process.env[key] = val;
	}
}

async function main(): Promise<void> {
	const { domain, arm, maxPerFramework, out } = parseArgs();
	loadEnv(path.join(SPYGLASSES, ".env.local"));
	loadEnv(path.join(SPYGLASSES, ".env"));

	const spyglassesCommit = execSync("git rev-parse HEAD", { cwd: SPYGLASSES }).toString().trim();

	const { crawlPages } = await import(`${SPYGLASSES}/packages/background-jobs/src/utils/page-extractor`);
	const { BrandSnapshotService } = await import(`${SPYGLASSES}/packages/core/src/services/brand-snapshot`);
	const { DiscoveryQueryService } = await import(`${SPYGLASSES}/packages/core/src/services/discovery-query`);

	console.log(`[003:${arm}] crawling ${domain} (max 5 pages)…`);
	const pages = await crawlPages(domain, 5);
	if (!pages.length) throw new Error(`crawled 0 pages from ${domain} — pick a different anchor domain`);
	console.log(`[003:${arm}] crawled ${pages.length} pages:\n  ${pages.map((p: { url: string }) => p.url).join("\n  ")}`);

	const sessionId = `aeo-exp003-${arm}`;
	const snapshot = await new BrandSnapshotService().generateBrandSnapshot(domain, pages, sessionId);
	console.log(`[003:${arm}] snapshot: name=${snapshot.name} category=${snapshot.category}`);

	const queries = await new DiscoveryQueryService().generateExpandedPrompts(
		snapshot,
		domain,
		FRAMEWORKS as never,
		sessionId,
		undefined,
		maxPerFramework,
	);
	console.log(`[003:${arm}] generated ${queries.length} queries across ${FRAMEWORKS.length} frameworks`);

	mkdirSync(out, { recursive: true });
	const outPath = path.join(out, `${arm}.json`);
	writeFileSync(
		outPath,
		JSON.stringify(
			{
				arm,
				domain,
				generated_at: new Date().toISOString(),
				spyglasses_commit: spyglassesCommit,
				generator_model: "claude-haiku-4-5",
				snapshot_model: "gpt-5-nano",
				frameworks: FRAMEWORKS,
				max_per_framework: maxPerFramework,
				crawled_urls: pages.map((p: { url: string }) => p.url),
				brand_snapshot: snapshot,
				queries: queries.map((q: { query: string; queryType: string; framework: string }) => ({
					query: q.query,
					queryType: q.queryType,
					framework: q.framework,
				})),
			},
			null,
			1,
		),
	);
	console.log(`[003:${arm}] wrote ${outPath}`);
}

main().then(
	() => process.exit(0),
	(err) => {
		console.error(err);
		process.exit(1);
	},
);
