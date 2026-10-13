---
license: apache-2.0
tags:
- stripedhyena
- long context
- deep signal processing
- hybrid
- biology
- genomics
task_categories:
  - text-generation
language:
  - en
pretty_name: open-genome
configs:
  - config_name: stage1
    data_files:
      - split: train
        path: 
          - "stage1/gtdb/gtdb_train_shard_*"
          - "stage1/imgpr/imgpr_train.parquet"
      - split: validation
        path: 
          - "stage1/gtdb/gtdb_valid_small.parquet"
          - "stage1/imgpr/imgpr_valid_small.parquet"
      - split: test
        path: 
          - "stage1/gtdb/gtdb_test.parquet"
          - "stage1/imgpr/imgpr_test.parquet"
  - config_name: stage2
    data_files:
      - split: train
        path: "stage2/train_stage2.parquet"
      - split: validation
        path: "stage2/valid_stage2.parquet"
      - split: test
        path: "stage2/test_stage2.parquet"
  - config_name: sample
    data_files:
      - split: validation
        path: "stage2/valid_stage2.parquet"
---



### Dataset organization

The OpenGenome dataset is organized in 2 stages, where stage 1 has context length 8k and stage 2 has context length 131k.  Each stage has their own datasplits.

```
- stage1
  - train
  - validation
  - test

- stage2
  - train
  - validation
  - test
```

### Instructions to download

You can load a dataset using HF's API, with an example below.

```
from datasets import load_dataset

stage1_data = load_dataset("LongSafari/open-genome", 'stage1')

# access just the train data
stage_1_train_data = stage1_data['train']

```

Note: stage 1 training dataset is sharded into separate files due to it's large size.

We also provide a small dataset sample to test out the pipeline if you prefer.

```
sample_data = load_dataset("LongSafari/open-genome", 'sample')['validation']

```

