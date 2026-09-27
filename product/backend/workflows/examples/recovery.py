# 以受控工作空间和内核身份恢复示例上下文；从不凭端口或同名项目接管进程。
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.process.tree import controller_for, kernel_tree_has_exited


class SampleRecovery:
    def __init__(self, factory, manager, clock):
        self._factory, self._manager, self._clock = factory, manager, clock

    def read(self):
        with self._factory() as work:
            workspace = work.sample_workspaces.latest()
            instance = None if workspace is None else work.sample_workspaces.instance(workspace["workspace_id"])
            observation = None if instance is None else work.sample_workspaces.observation(instance["instance_id"])
            project = None if workspace is None or workspace["project_id"] is None else work.projects.get(workspace["project_id"])
        return workspace, instance, observation, project

    def reconcile(self):
        workspace, instance, _, _ = self.read()
        if workspace is None or instance is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "旧环境没有可核验的实例所有权记录；请保留历史并人工确认旧进程")
        identity = instance["kernel_identity"]
        # Windows Job 名称必须与持久实例完全一致，拒绝任意名称和不可排除复用的 PID 身份。
        supported = identity == {"kind": "windows-job", "name": f"jiejian-sample-{instance['instance_id']}"}
        try:
            exited = supported and kernel_tree_has_exited(identity)
        except OSError:
            exited = False
        outcome = "EXITED" if exited else "OWNERSHIP_UNCONFIRMED"
        with self._factory() as work:
            work.sample_workspaces.observe(dict(reconciliation_id=uuid4().hex,
                instance_id=instance["instance_id"], observed_at_us=self._clock(), outcome=outcome))
            work.commit()
        return outcome

    def confirm_owned(self, runtime):
        """只有当前控制者仍持有同一内核树时确认可控；不把历史运行记录当成接管凭据。"""
        workspace, instance, _, _ = self.read()
        controller = controller_for(runtime.process)
        if (workspace is None or instance is None or instance["instance_id"] != runtime.experience_id
                or controller is None or controller.has_exited()
                or controller.kernel_identity != instance["kernel_identity"]
                or workspace["source_root"] != str(runtime.source_root)):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前实例的控制权与持久记录不一致")
        with self._factory() as work:
            work.sample_workspaces.observe(dict(reconciliation_id=uuid4().hex,
                instance_id=instance["instance_id"], observed_at_us=self._clock(), outcome="OWNED_RUNNING"))
            work.commit()

    def create(self):
        workspace_id = f"wsp_{uuid4().hex}"
        value = dict(workspace_id=workspace_id, project_id=None,
            source_root=str(self._manager.workspace_source(workspace_id)), scenario_version="BASELINE", created_at_us=self._clock())
        with self._factory() as work:
            work.sample_workspaces.save(value)
            work.commit()
        return value

    def launched(self, workspace, runtime):
        controller = controller_for(runtime.process)
        identity = {} if controller is None else controller.kernel_identity
        with self._factory() as work:
            work.sample_workspaces.add_instance(runtime.experience_id, workspace["workspace_id"], identity, self._clock())
            work.commit()

    def save(self, workspace):
        with self._factory() as work:
            work.sample_workspaces.save(workspace)
            work.commit()
