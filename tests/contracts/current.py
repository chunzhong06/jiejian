# 经产品设计接受的当前合同；独立列出预期，不从被测实现复制答案。
DATABASE_HEAD = "0012_proof_preparation"
WORKER_CAPABILITIES = ("CHECK", "PROOF_PREFLIGHT", "RECORDING")
JOB_TARGET_FIELDS = frozenset({"run_id", "recording_id", "runtime_load_id", "preflight_id"})
