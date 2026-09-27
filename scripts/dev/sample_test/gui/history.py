# 历史查询与精确记录返回的真实页面操作。
from urllib.parse import parse_qs, urlsplit
from .session import GuiSession


class HistoryActions(GuiSession):
    def history_search(self, project, run_id):
        from scripts.dev.sample_test.harness.state import SampleTestError
        self._goto("/history")
        self.page.get_by_role("textbox", name="搜索检查历史", exact=True).fill(run_id)
        with self.page.expect_response(lambda response: response.request.method == "GET"
                and urlsplit(response.url).path == f"/api/projects/{project}/check-history"
                and parse_qs(urlsplit(response.url).query).get("query") == [run_id]) as response:
            self.page.get_by_role("button", name="搜索", exact=True).click()
        data = response.value.json().get("data", {})
        if response.value.status != 200 or data.get("project_id") != project or [item["status"]["run"]["run_id"] for item in data.get("items", [])] != [run_id]:
            raise SampleTestError("GUI_HISTORY_SEARCH_MISMATCH")
        self.page.locator(f'[data-run="{run_id}"]').wait_for()
        if self.page.locator("[data-run]:visible").evaluate_all("nodes => nodes.map(node => node.dataset.run)") != [run_id]:
            raise SampleTestError("GUI_HISTORY_ROWS_MISMATCH")
        self.capture("history")
        self._mark("history-search")

    def history_open(self, result):
        self.page.locator(f'[data-run="{result["run_id"]}"]').click()
        self._exact_history_result(result)

    def _exact_history_result(self, result):
        def matches(url):
            route, _, query = urlsplit(str(url)).fragment.partition("?")
            return route == "/history" and parse_qs(query).get("run_id") == [result["run_id"]]
        self.page.wait_for_url(matches)
        self.page.get_by_role("heading", name=result["story"]["judgement"], level=1, exact=True).wait_for()

    def history_return(self, query):
        from scripts.dev.sample_test.harness.state import SampleTestError
        self.page.get_by_role("button", name="返回检查历史", exact=True).click()
        self.page.get_by_role("textbox", name="搜索检查历史", exact=True).wait_for()
        if (self.page.get_by_role("textbox", name="搜索检查历史", exact=True).input_value() != query
                or self.page.locator("[data-run]:visible").evaluate_all("nodes => nodes.map(node => node.dataset.run)") != [query]):
            raise SampleTestError("GUI_HISTORY_RETURN_STATE_LOST")
        self._mark("history-return")
