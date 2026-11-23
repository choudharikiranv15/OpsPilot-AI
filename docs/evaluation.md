# Diagnosis evaluation

`scripts/eval_diagnosis.py` runs the diagnosis on 12 realistic failures (missing packages, a type error, a syntax error, database and Redis failures, OOM, a missing environment variable, a permission error, a Go nil pointer, an upstream 503, a full disk) and measures:

- **schema-valid**: the model returned usable structured output
- **cites a real fact**: the top hypothesis cites at least one extracted fact
- **category accuracy**: the top hypothesis' root-cause category is one of the acceptable ones for that case

Run it against any configured provider:

```bash
python scripts/eval_diagnosis.py                 # default local model
python scripts/eval_diagnosis.py --model llama3  # another Ollama model
python scripts/eval_diagnosis.py --markdown results.md
```

This is a small regression check, not a benchmark. Twelve cases cannot measure fine differences between models, and the category labels are a proxy for "the answer points the right way".

## Results (2026-11-23, OpsPilot 0.2.0.dev0, local Ollama on a Windows laptop, CPU)

| Model | Schema-valid | Cites a real fact | Category accuracy | Median time/case |
|---|---|---|---|---|
| `llama3.2` (3B), before category fix | 12/12 | 12/12 | 6/12 (50%) | ~8 s |
| `llama3.2` (3B) | 12/12 | 12/12 | 9/12 (75%) | ~8 s |
| `llama3` (8B) | 12/12 | 12/12 | 11/12 (92%) | ~18 s |

The first row is the baseline that motivated a change: the 3B model copied the `a|b|c` enum syntax from the prompt (e.g. `database|network`) or invented labels. Listing the categories explicitly and normalising the model's answer in code raised accuracy from 50% to 75% with the same model.

### Per-case details

### ollama / llama3.2

- **schema-valid:** 12/12 (100%)
- **top hypothesis cites a real fact:** 12/12 (100%)
- **category accuracy:** 9/12 (75%)
- **median time per case:** 7.5s

| Case | Expected | Got | Cites a fact | Top hypothesis |
|---|---|---|---|---|
| python-missing-module | dependency | dependency | yes | Missing or incompatible package |
| node-module-not-found | build, dependency | dependency | yes | Missing or incompatible package |
| typescript-type-error | build, code_bug | dependency ✗ | yes | Type mismatch in dependency |
| postgres-connection-refused | database, external_service, network | configuration ✗ | yes | Database connection failed due to missing or incorrect configuration |
| redis-timeout | database, external_service, network, resource_exhaustion | resource_exhaustion | yes | Redis connection failed due to timeout |
| java-out-of-memory | resource_exhaustion | resource_exhaustion | yes | Resource Exhaustion: Insufficient Memory |
| missing-env-var | configuration | configuration | yes | Missing or wrong configuration setting |
| permission-denied | configuration, permissions | permissions | yes | Insufficient permissions to write to the log file |
| python-syntax-error | build, code_bug | dependency ✗ | yes | Missing or incompatible package |
| go-nil-pointer | code_bug | code_bug | yes | Invalid memory access |
| upstream-503 | external_service, network | external_service | yes | Payment API failure led to generic build error |
| disk-full | resource_exhaustion | resource_exhaustion | yes | Insufficient disk space led to an OSError during the build process. |

### ollama / llama3

- **schema-valid:** 12/12 (100%)
- **top hypothesis cites a real fact:** 12/12 (100%)
- **category accuracy:** 11/12 (92%)
- **median time per case:** 18.7s

| Case | Expected | Got | Cites a fact | Top hypothesis |
|---|---|---|---|---|
| python-missing-module | dependency | dependency | yes | Missing Redis module |
| node-module-not-found | build, dependency | dependency | yes | 'express' module not found |
| typescript-type-error | build, code_bug | code_bug | yes | TypeScript error in code |
| postgres-connection-refused | database, external_service, network | resource_exhaustion ✗ | yes | PostgreSQL service is not running or not listening on default port |
| redis-timeout | database, external_service, network, resource_exhaustion | resource_exhaustion | yes | Redis connection issues |
| java-out-of-memory | resource_exhaustion | resource_exhaustion | yes | resource_exhaustion |
| missing-env-var | configuration | configuration | yes | Missing or incorrect DATABASE_URL environment variable |
| permission-denied | configuration, permissions | permissions | yes | Insufficient permissions for the log file |
| python-syntax-error | build, code_bug | code_bug | yes | Code bug |
| go-nil-pointer | code_bug | code_bug | yes | Code bug: incorrect memory access |
| upstream-503 | external_service, network | external_service | yes | external_service |
| disk-full | resource_exhaustion | resource_exhaustion | yes | Resource exhaustion |
