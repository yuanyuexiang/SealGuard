# sealguard-ai / siamese

Two complementary ways to give the API a real Siamese encoder:

## A. Out-of-the-box: DINOv2-small ONNX (no training)

```bash
cd sealguard-ai/siamese
pip install -r requirements.txt
python export_dinov2.py \
  --output ../../sealguard-api/artifacts/siamese/model/siamese_best.onnx
```

Then in the API environment:

```bash
export SIAMESE_WEIGHTS_PATH=./artifacts/siamese/model/siamese_best.onnx
export SIAMESE_INPUT_SIZE=224
export SIAMESE_EMBEDDING_DIM=384
# restart API, then rebuild prototypes:
curl -X POST 'http://localhost:8001/api/templates/rebuild-embeddings?force=true'
```

The matcher's `.onnx` branch applies ImageNet normalisation internally and
takes the CLS token out of the ViT output.

## B. Train your own on the templates table

```bash
cd sealguard-ai/siamese
pip install -r requirements.txt
PYTHONPATH=../../sealguard-api python train.py \
  --database-url postgresql+psycopg2://postgres:123456@localhost:5432/sealguard \
  --runtime-dir ../../sealguard-api/runtime \
  --output ../../sealguard-api/artifacts/siamese/model/siamese_best.ts \
  --epochs 30
```

The training script samples natural triplets from the templates table:

| role     | source                                                                |
|----------|-----------------------------------------------------------------------|
| anchor   | random template row                                                   |
| positive | another row with the same `(customer_id, type)`; else strong aug      |
| negative | a row with the same `type` but a different `customer_id`              |

Backbone is MobileNetV3-Small with ImageNet weights, projection head emits
a 128-d L2-normalised embedding. ImageNet mean/std is baked into the
exported TorchScript so the API loader needs no special preprocessing.

After training:

```bash
export SIAMESE_WEIGHTS_PATH=./artifacts/siamese/model/siamese_best.ts
export SIAMESE_EMBEDDING_DIM=128
curl -X POST 'http://localhost:8001/api/templates/rebuild-embeddings?force=true'
```

## When to use which

- Just deployed, no labelled data, want a quick lift — **A (DINOv2 ONNX)**.
- Have ≥ a few hundred templates spread across ≥ ~10 customers and want a
  domain-tuned encoder — **B (train your own)**.
- Both are compatible with the prototype + adaptive-threshold pipeline; you
  can switch back and forth by changing `SIAMESE_WEIGHTS_PATH` and
  rebuilding prototypes.
