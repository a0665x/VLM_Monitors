#!/usr/bin/env python3
"""Measure a fixed local image, one cold request then N warm requests."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from adapters.inference_client import create_inference_client, backend_name, default_model


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be at least 1')
    images = sorted(args.image.glob("*.jpg")) if args.image.is_dir() else [args.image]
    if not images:
        parser.error('No JPEG files found')
    if len(images) > 1 and len(images) < args.runs + 1:
        parser.error('An image sequence needs at least runs + 1 frames')
    client = create_inference_client()
    runs = []
    for i in range(args.runs + 1):
        raw = images[min(i, len(images)-1)].read_bytes()
        start = time.perf_counter()
        result = await client.generate('Describe the image accurately. Use one short sentence.', 'What is visible in this image?', raw)
        record = {'phase':'first' if i == 0 else 'warm', 'image_sha256':hashlib.sha256(raw).hexdigest(), 'wall_ms':round((time.perf_counter()-start)*1000), 'text':result.text}
        runs.append(record)
        print(json.dumps(record,ensure_ascii=False), flush=True)
    data = {'backend':backend_name(), 'model':default_model(), 'input_mode':'sequence' if len(images)>1 else 'repeated_image',
            'max_tokens':int(os.getenv('VLM_MAX_TOKENS','128')), 'temperature':float(os.getenv('VLM_TEMPERATURE','0')),
            'warm_median_ms':statistics.median(r['wall_ms'] for r in runs[1:]), 'runs':runs}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

if __name__ == '__main__':
    asyncio.run(main())
