# 跨领域、协议与存储复用的公共标识符格式。

PROJECT_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
LONG_SLUG_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,127}$"
RUN_ID_PATTERN = r"^run_[0-9a-f]{32}$"
JOB_ID_PATTERN = r"^job_[0-9a-f]{32}$"
RECORDING_ID_PATTERN = r"^rec_[0-9a-f]{32}$"
TEST_IDENTITY_ID_PATTERN = r"^tid_[0-9a-f]{32}$"
EVIDENCE_ID_PATTERN = r"^ev_[0-9a-f]{20,64}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
REQUIREMENT_ID_PATTERN = r"^req_[0-9a-f]{32}$"
CANDIDATE_ID_PATTERN = r"^cand_[0-9a-f]{32}$"
