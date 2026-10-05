# 核对权限行可见高亮与跨动作分组的连续位移，避免仅验证静止终态。
import base64


def permission_editor(project_id: str) -> dict:
    """提供已确认权限的只读显示夹具，不提交权限提案或批准。"""
    actors = [{"actor_id": key, "revision": 1, "display_name": label,
               "description": "界面验收资料", "effective_state": "ACTIVE"}
              for key, label in [("owner", "项目负责人"), ("member", "普通成员")]]
    action = {"action_id": "export", "revision": 1, "display_name": "导出项目包",
              "description": "形成交付包", "primary_resource_concept": "项目",
              "operation_kind": "EXPORT", "state_changing": True, "effective_state": "ACTIVE",
              "effect_catalog": [{"effect_id": "package", "business_label": "项目包真实形成",
                                  "effect_kind": "OBJECT_CREATION", "resource_concept": "项目包",
                                  "protected_projection": [], "description": "项目包已形成"}]}
    rules = [{"intent_id": f"rule-{index}", "revision": 1, "intent_hash": str(index) * 64,
              "subject_actor_id": actor, "subject_actor_revision": 1,
              "business_action_id": "export", "action_revision": 1,
              "resource_owner_actor_id": "owner", "resource_owner_actor_revision": 1,
              "relation": relation, "expectation": expectation,
              "protected_effect_ids": ["package"], "effective_state": "ACTIVE"}
             for index, (actor, relation, expectation) in enumerate([
                 ("owner", "OWNS", "ALLOW"), ("member", "OTHER_ROLE", "DENY")])]
    boundary = {"project_id": project_id, "policy_epoch": 1, "actors": actors,
                "actions": [action], "actor_bindings": [], "action_bindings": [],
                "permission_intents": rules, "permission_statuses": [{"action_id": "export",
                "action_revision": 1, "permission_semantics_confirmed": True,
                "active_permission_count": 2, "stale_permission_count": 0,
                "allow_control_available": True, "reason_codes": []}]}
    # 前两条属于导出、第三条属于归档，覆盖跨分组时不能重建高亮层的情形。
    boundary["actions"].append({**action, "action_id": "archive", "display_name": "归档项目包"})
    rules.append({**rules[0], "intent_id": "rule-archive", "business_action_id": "archive"})
    boundary["permission_statuses"].append({**boundary["permission_statuses"][0], "action_id": "archive", "active_permission_count": 1})
    return {"project_id": project_id, "boundary": boundary,
            "preview": {"project_id": project_id, "application_understanding_revision": 1, "candidates": []},
            "maintenance_draft": {"project_id": project_id, "boundary_state_fingerprint": "ui-check",
                "actors": [], "actions": [], "permissions": [], "candidate_options": [], "implementation_inspections": []},
            "boundary_state_fingerprint": "ui-check", "pending_proposals": [], "pending_has_more": False}


def verify_permission_feedback(page, out, label: str) -> dict:
    """取行内左侧留白，排除文字下划线、状态图标和焦点框造成的假阳性。"""
    row = page.locator(".light-permission-list .permission-summary-row").first
    row.wait_for(state="visible")
    row.evaluate("e => e.scrollIntoView({block: 'center'})")
    page.mouse.move(0, 0)
    before = row.screenshot(animations="disabled")
    images = {"before": before}
    row.hover()
    page.wait_for_timeout(450)
    images["hover"] = row.screenshot(animations="disabled")
    page.mouse.move(0, 0)
    row.get_by_role("button", name="详情", exact=True).focus()
    page.wait_for_timeout(450)
    images["focus"] = row.screenshot(animations="disabled")
    row.get_by_role("button", name="详情", exact=True).press("Shift+Tab")
    row.evaluate("e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(450)
    images["leave"] = row.screenshot(animations="disabled")
    for state, data in images.items():
        (out / f"permission-{label}-{state}.png").write_bytes(data)
    samples = page.evaluate("""async images => {
      const pairs = await Promise.all(Object.entries(images).map(async ([key, data]) => {
        const image = new Image(); image.src = 'data:image/png;base64,' + data; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
        return [key, [.25,.5,.75].map(y => [...ctx.getImageData(8, Math.floor(image.height*y), 1, 1).data].slice(0,3))];
      })); return Object.fromEntries(pairs);
    }""", {state: base64.b64encode(data).decode() for state, data in images.items()})
    differences = {state: max(abs(a-b) for first, second in zip(samples["before"], values)
                             for a, b in zip(first, second)) for state, values in samples.items()}
    assert differences["hover"] >= 5, ("PERMISSION_HOVER_NOT_VISIBLE", samples)
    assert differences["focus"] >= 5, ("PERMISSION_FOCUS_NOT_VISIBLE", samples)
    assert differences["leave"] <= 2, ("PERMISSION_HIGHLIGHT_NOT_CLEARED", samples)
    transitions = verify_row_transitions(page, ".light-permission-list", ".permission-summary-row")
    return {"background_difference": differences, "samples": samples, "transitions": transitions}


def verify_row_transitions(page, host_selector: str, row_selector: str) -> list[dict]:
    """采样相邻、跨组及反向移动的中间帧；终点颜色正确不能替代连续位移。"""
    host = page.locator(host_selector).filter(visible=True).first
    rows = host.locator(row_selector)
    assert rows.count() >= 3
    full = page.locator("html").get_attribute("data-motion") == "full"
    position = lambda: host.evaluate("e => new DOMMatrixReadOnly(getComputedStyle(e,'::before').transform).m42")
    rows.first.hover()
    page.wait_for_timeout(450)
    transitions = []
    for index in [1, 2, 0]:
        before = position()
        rows.nth(index).hover()
        page.wait_for_timeout(70)
        assert host.get_attribute("data-motion-hover") == "true"
        assert host.locator('[data-motion-hover=true]').count() == 0
        target = host.evaluate("e => parseFloat(e.style.getPropertyValue('--row-y'))")
        middle = position()
        if full:
            assert min(before, target)+.5 < middle < max(before, target)-.5, (before, middle, target)
        page.wait_for_timeout(450)
        after = position()
        assert abs(after-target) < 1, (after, target)
        transitions.append({"row": index, "before": before, "middle": middle, "target": target, "after": after, "full_motion": full})
    page.mouse.move(0, 0)
    page.wait_for_timeout(450)
    assert host.evaluate("e => getComputedStyle(e,'::before').opacity") == "0"
    return transitions
