# product/frontend/src/shared 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

| 文件 | 行数 | 公开声明 |
| --- | ---: | --- |
| [product/frontend/src/shared/api/http.ts](../../../product/frontend/src/shared/api/http.ts) | 101 | ApiEnvelope、ApiError、ErrorDiagnosis、request |
| [product/frontend/src/shared/lib/contentTransition.ts](../../../product/frontend/src/shared/lib/contentTransition.ts) | 26 | useContentTransition |
| [product/frontend/src/shared/lib/directoryState.ts](../../../product/frontend/src/shared/lib/directoryState.ts) | 33 | useDirectoryState |
| [product/frontend/src/shared/lib/format.ts](../../../product/frontend/src/shared/lib/format.ts) | 2 | date、text |
| [product/frontend/src/shared/lib/id.ts](../../../product/frontend/src/shared/lib/id.ts) | 2 | prefixedId |
| [product/frontend/src/shared/lib/inputMode.ts](../../../product/frontend/src/shared/lib/inputMode.ts) | 17 | trackInputMode |
| [product/frontend/src/shared/lib/motionTiming.ts](../../../product/frontend/src/shared/lib/motionTiming.ts) | 5 | motionMilliseconds |
| [product/frontend/src/shared/lib/navigation.ts](../../../product/frontend/src/shared/lib/navigation.ts) | 51 | Route、checkPlanDestination、go、historyLocation、readRoute、returnDestination、returnDestinationLabel、scopedPath等 |
| [product/frontend/src/shared/lib/operations.ts](../../../product/frontend/src/shared/lib/operations.ts) | 51 | operationId、readPending、savePending、useCommand |
| [product/frontend/src/shared/lib/pageRefresh.ts](../../../product/frontend/src/shared/lib/pageRefresh.ts) | 23 | refreshCurrentPage、subscribePageRefresh、usePageRefresh |
| [product/frontend/src/shared/lib/pageTransition.ts](../../../product/frontend/src/shared/lib/pageTransition.ts) | 44 | commitPageTransition、commitThemeTransition、pageTransitionActive |
| [product/frontend/src/shared/lib/routePage.tsx](../../../product/frontend/src/shared/lib/routePage.tsx) | 29 | routePage |
| [product/frontend/src/shared/lib/routes.ts](../../../product/frontend/src/shared/lib/routes.ts) | 20 | RouteDefinition、routeAliases、routeDefinition、routes |
| [product/frontend/src/shared/lib/selectionIndicator.ts](../../../product/frontend/src/shared/lib/selectionIndicator.ts) | 64 | useSelectionIndicator |
| [product/frontend/src/shared/lib/settings.ts](../../../product/frontend/src/shared/lib/settings.ts) | 12 | SettingsSection、settingsPath、settingsSection、settingsSections |
| [product/frontend/src/shared/lib/useRead.ts](../../../product/frontend/src/shared/lib/useRead.ts) | 50 | useRead |
| [product/frontend/src/shared/lib/workflow.tsx](../../../product/frontend/src/shared/lib/workflow.tsx) | 7 | WorkflowContext、WorkflowNavigation、useWorkflow |
| [product/frontend/src/shared/model/page.ts](../../../product/frontend/src/shared/model/page.ts) | 5 | PageProps、assertProject |
| [product/frontend/src/shared/styles/controls.css](../../../product/frontend/src/shared/styles/controls.css) | 90 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/cross-page.css](../../../product/frontend/src/shared/styles/cross-page.css) | 8 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/foundation.css](../../../product/frontend/src/shared/styles/foundation.css) | 155 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/loading.css](../../../product/frontend/src/shared/styles/loading.css) | 17 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/motion.css](../../../product/frontend/src/shared/styles/motion.css) | 132 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/navigation.css](../../../product/frontend/src/shared/styles/navigation.css) | 11 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/patterns.css](../../../product/frontend/src/shared/styles/patterns.css) | 119 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/shapes.css](../../../product/frontend/src/shared/styles/shapes.css) | 21 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/tokens.css](../../../product/frontend/src/shared/styles/tokens.css) | 148 | 包、内部机制或样式 |
| [product/frontend/src/shared/styles/workspaces.css](../../../product/frontend/src/shared/styles/workspaces.css) | 69 | 包、内部机制或样式 |
| [product/frontend/src/shared/ui/actions.tsx](../../../product/frontend/src/shared/ui/actions.tsx) | 30 | ActionLink、Button |
| [product/frontend/src/shared/ui/Choice.tsx](../../../product/frontend/src/shared/ui/Choice.tsx) | 21 | Choice |
| [product/frontend/src/shared/ui/CommandMenu.tsx](../../../product/frontend/src/shared/ui/CommandMenu.tsx) | 50 | CommandMenu |
| [product/frontend/src/shared/ui/ComparePair.tsx](../../../product/frontend/src/shared/ui/ComparePair.tsx) | 6 | ComparePair |
| [product/frontend/src/shared/ui/Dialog.tsx](../../../product/frontend/src/shared/ui/Dialog.tsx) | 28 | Dialog |
| [product/frontend/src/shared/ui/DirectoryField.css](../../../product/frontend/src/shared/ui/DirectoryField.css) | 4 | 包、内部机制或样式 |
| [product/frontend/src/shared/ui/DirectoryField.tsx](../../../product/frontend/src/shared/ui/DirectoryField.tsx) | 10 | DirectoryField |
| [product/frontend/src/shared/ui/DisclosureMarker.tsx](../../../product/frontend/src/shared/ui/DisclosureMarker.tsx) | 5 | DisclosureMarker |
| [product/frontend/src/shared/ui/feedback.tsx](../../../product/frontend/src/shared/ui/feedback.tsx) | 28 | Badge、Empty、ErrorNote、FeedbackTone、Loading、Notice、PageError、ResultList等 |
| [product/frontend/src/shared/ui/FilePicker.css](../../../product/frontend/src/shared/ui/FilePicker.css) | 18 | 包、内部机制或样式 |
| [product/frontend/src/shared/ui/FilePicker.tsx](../../../product/frontend/src/shared/ui/FilePicker.tsx) | 57 | FilePicker |
| [product/frontend/src/shared/ui/Hint.tsx](../../../product/frontend/src/shared/ui/Hint.tsx) | 20 | Hint |
| [product/frontend/src/shared/ui/IndexSelection.css](../../../product/frontend/src/shared/ui/IndexSelection.css) | 26 | 包、内部机制或样式 |
| [product/frontend/src/shared/ui/IndexSelection.tsx](../../../product/frontend/src/shared/ui/IndexSelection.tsx) | 16 | IndexActions、IndexSelection |
| [product/frontend/src/shared/ui/Inspector.tsx](../../../product/frontend/src/shared/ui/Inspector.tsx) | 18 | Inspector |
| [product/frontend/src/shared/ui/layout.tsx](../../../product/frontend/src/shared/ui/layout.tsx) | 35 | Field、FormColumns、Heading、ObjectHeading、ObjectIdentity、SectionHeading |
| [product/frontend/src/shared/ui/ObjectTable.css](../../../product/frontend/src/shared/ui/ObjectTable.css) | 5 | 包、内部机制或样式 |
| [product/frontend/src/shared/ui/ObjectTable.tsx](../../../product/frontend/src/shared/ui/ObjectTable.tsx) | 14 | ObjectTable |
| [product/frontend/src/shared/ui/overlay.ts](../../../product/frontend/src/shared/ui/overlay.ts) | 3 | popupParent |
| [product/frontend/src/shared/ui/PageSkeleton.tsx](../../../product/frontend/src/shared/ui/PageSkeleton.tsx) | 18 | PageSkeleton |
| [product/frontend/src/shared/ui/PageSurface.tsx](../../../product/frontend/src/shared/ui/PageSurface.tsx) | 38 | PageSurface |
| [product/frontend/src/shared/ui/PasswordInput.tsx](../../../product/frontend/src/shared/ui/PasswordInput.tsx) | 13 | PasswordInput |
| [product/frontend/src/shared/ui/Progress.tsx](../../../product/frontend/src/shared/ui/Progress.tsx) | 4 | Progress |
| [product/frontend/src/shared/ui/SearchField.css](../../../product/frontend/src/shared/ui/SearchField.css) | 10 | 包、内部机制或样式 |
| [product/frontend/src/shared/ui/SearchField.tsx](../../../product/frontend/src/shared/ui/SearchField.tsx) | 15 | SearchField |
| [product/frontend/src/shared/ui/Segmented.tsx](../../../product/frontend/src/shared/ui/Segmented.tsx) | 14 | Segmented |
| [product/frontend/src/shared/ui/Switch.tsx](../../../product/frontend/src/shared/ui/Switch.tsx) | 10 | Switch |
| [product/frontend/src/shared/ui/Tabs.css](../../../product/frontend/src/shared/ui/Tabs.css) | 53 | 包、内部机制或样式 |
| [product/frontend/src/shared/ui/Tabs.tsx](../../../product/frontend/src/shared/ui/Tabs.tsx) | 19 | LinkTabs、Tabs |
| [product/frontend/src/shared/ui/TaskSurface.tsx](../../../product/frontend/src/shared/ui/TaskSurface.tsx) | 14 | TaskSurface |
| [product/frontend/src/shared/ui/WorkflowSteps.tsx](../../../product/frontend/src/shared/ui/WorkflowSteps.tsx) | 14 | WorkflowStep、WorkflowSteps |
