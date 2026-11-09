import asyncio
from datetime import datetime, timezone
import json
import math
import platform
import statistics
import time

from engine import catalog as movie_catalog
from engine import constants
from engine import services
from engine.stores import factory
from evaluation.config import paths
from evaluation.config import settings


async def evaluate():
    store = factory.create_store(**settings.store_settings())
    try:
        data = movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)
        titles = {m['id']:m['translations']['en']['title'] for m in data}
        queries = json.loads((paths.DATA_PATH/'queries.json').read_text())['queries']
        baseline = json.loads((paths.DATA_PATH/'legacy.json').read_text())
        results = []
        for case in queries:
            start = time.perf_counter()
            response = await services.semantic_search(store,case['query'],limit=5)
            elapsed = time.perf_counter()-start
            ids = [p['id'] for p in response['recommendations']]
            relevant = set(case['relevant_ids'])
            results.append({**case, 'top_5_ids':ids,
                            'recall_at_5':len(set(ids)&relevant)/len(relevant),
                            'seconds':elapsed})
        comparisons = []
        for source, old in baseline['qdrant_recommendations'].items():
            response = await store.recommend(int(source))
            ids = [p['id'] for p in response['recommendations']]
            old_ids = [p['id'] for p in old]
            comparisons.append({'source_id':int(source),'legacy_ids':old_ids,'semantic_ids':ids,
                                'overlap_at_5':len(set(ids)&set(old_ids))/5})
        latencies = sorted(r['seconds'] for r in results[1:])
        report = {
            'recorded_at':datetime.now(timezone.utc).isoformat(),
            'platform':platform.platform(), 'python':platform.python_version(),
            'model':store.spec.metadata(), 'tei_info':await store.embeddings.check_model(),
            'recall_at_5': {lang:statistics.mean(r['recall_at_5'] for r in results if lang == 'all' or r['lang']==lang)
                            for lang in ('all','en','ru')},
            'latency_seconds':{'first':results[0]['seconds'],'subsequent_n':len(latencies),
                               'min':min(latencies),'median':statistics.median(latencies),
                               'p95':latencies[math.ceil(.95*len(latencies))-1]},
            'queries':results, 'recommendation_comparisons':comparisons,
        }
        (paths.RESULTS_PATH/'results-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        lines = ['# Local evaluation results', '',
                 f"Recorded: {report['recorded_at']}. Host: {report['platform']}; Python {report['python']}.",
                 '', 'Protocol and frozen judgments: [README](README.md), [queries](data/queries.json).',
                 'Full measurements and model identity: [results.json](results/results-latest.json).', '',
                 f"Mean Recall@5: **{report['recall_at_5']['all']:.3f}** "
                 f"(EN {report['recall_at_5']['en']:.3f}, RU {report['recall_at_5']['ru']:.3f}).", '',
                 'These are 20 hand-selected queries with ten paired plot intents, not independent',
                 'samples or a broad benchmark. Many closely paraphrase the short catalog descriptions.',
                 'They verify retrieval behavior and do not establish a guaranteed quality improvement.', '',
                 '| Query | Relevant IDs | Top 5 IDs | Recall@5 |',
                 '| --- | --- | --- | --- |']
        for r in results:
            lines.append(f"| {r['id']} | {r['relevant_ids']} | {r['top_5_ids']} | {r['recall_at_5']:.2f} |")
        latency = report['latency_seconds']
        lines += ['', f"First description request: {latency['first']*1000:.1f} ms. "
                  f"Subsequent {len(latencies)}: min {latency['min']*1000:.1f}, "
                  f"median {latency['median']*1000:.1f}, p95 {latency['p95']*1000:.1f} ms.",
                  'The server was already ready and had served earlier verification requests.',
                  'First means first in this evaluation client, not a cold model.',
                  'Timings include /info compatibility checks, TEI and Qdrant; they exclude HTML rendering.', '',
                  '## Recommendation comparison', '',
                  '| Source | Legacy top 5 | Semantic top 5 | Overlap@5 |',
                  '| --- | --- | --- | --- |']
        for r in comparisons:
            names = lambda ids: ', '.join(titles[i] for i in ids)
            lines.append(f"| {titles[r['source_id']]} | {names(r['legacy_ids'])} | {names(r['semantic_ids'])} | {r['overlap_at_5']:.1f} |")
        lines += ['', '## Limitations and weak cases', '']
        weak = [r for r in results if r['recall_at_5'] < 1]
        for r in weak:
            missing = sorted(set(r['relevant_ids'])-set(r['top_5_ids']))
            lines.append(f"- {r['id']}: missing {missing} at rank 5 for “{r['query']}”.")
        if not weak:
            lines.append('All judged relevant IDs were retrieved in this narrow set. This does not cover ambiguous, negative, or multi-constraint requests.')
        lines += ['', 'Recommendation overlap measures change, not preference quality. Inspect the lists:',
                  'semantic similarity can emphasize plot objects or franchise titles rather than mood.',
                  'The descriptions are one sentence long; missing details cannot reliably be recovered.',
                  'There is no personalization, reranker, hybrid retrieval, or training in this version.', '']
        (paths.PACKAGE_PATH/'REPORT-latest.md').write_text('\n'.join(lines))
        print(json.dumps({'recall_at_5':report['recall_at_5'],'latency_seconds':latency},indent=2))
    finally:
        await store.close()


if __name__ == '__main__':
    asyncio.run(evaluate())
