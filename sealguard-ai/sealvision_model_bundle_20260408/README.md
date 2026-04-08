# SealVision 模型迁移包

这个目录可直接复制到其他项目中使用。

## 目录结构

- model/sealvision_best.pt: 已训练权重（推荐部署使用）
- tools/predict.py: 本地推理脚本（基于 Ultralytics）
- docs/classes.yaml: 类别映射
- requirements.txt: 最小依赖

## 快速开始

1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

2. 单张图片推理

```bash
python3 tools/predict.py \
  --weights model/sealvision_best.pt \
  --source /path/to/image.jpg \
  --device cpu \
  --save \
  --name demo_single
```

3. 文件夹批量推理

```bash
python3 tools/predict.py \
  --weights model/sealvision_best.pt \
  --source /path/to/images \
  --device cpu \
  --save \
  --save-txt \
  --name demo_batch
```

输出目录默认在 runs/predict/<name>。

## 类别映射（务必保持一致）

- 0: signature
- 1: stamp

## 参数建议

- 默认参数: imgsz=960, conf=0.25
- 如果速度优先: imgsz 可改为 640
- 如果误检较多: conf 可提高到 0.35 或 0.4

## 迁移到其他项目

将整个目录复制到目标项目后，按上面命令运行即可。
如果目标项目已有自己的推理流程，只需要至少保留：

- model/sealvision_best.pt
- docs/classes.yaml

并在目标代码中按相同类别映射解释输出。
