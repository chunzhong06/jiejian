// 让编辑器中的正式前端源码复用 var 受控工作区的依赖解析，不参与 tsc、构建或运行。

"use strict";

const path = require("node:path");

function init(modules) {
  const ts = modules.typescript;

  function create(info) {
    const host = info.languageServiceHost;
    const originalResolve = host.resolveModuleNameLiterals?.bind(host);
    const originalCachedResolve =
      host.getResolvedModuleWithFailedLookupLocationsFromCache?.bind(host);
    const compilerOptions = host.getCompilationSettings();
    const configPath = compilerOptions.configFilePath || info.project.getProjectName();
    const projectRoot = path.dirname(configPath);
    const sourceRoot = path.resolve(
      projectRoot,
      typeof info.config.sourceRoot === "string" ? info.config.sourceRoot : ".",
    );
    const configuredWorkspace = path.resolve(
      projectRoot,
      typeof info.config.workspaceRoot === "string"
        ? info.config.workspaceRoot
        : "../../var/runtime/build/frontend-workspace",
    );
    // 在生成工作区内打开文件时优先使用当前目录；在正式源码中才投影到 var。
    const workspaceRoot = ts.sys.directoryExists(path.join(projectRoot, "node_modules"))
      ? projectRoot
      : configuredWorkspace;
    const workspaceModules = path.join(workspaceRoot, "node_modules");
    const canonicalFileName = ts.createGetCanonicalFileName(
      ts.sys.useCaseSensitiveFileNames,
    );
    const resolutionCache = ts.createModuleResolutionCache(
      workspaceRoot,
      canonicalFileName,
      compilerOptions,
    );

    function projectedContainingFile(containingFile) {
      if (!ts.sys.directoryExists(workspaceModules)) {
        return undefined;
      }
      const relative = path.relative(sourceRoot, path.resolve(containingFile));
      if (
        relative === ".." ||
        relative.startsWith(`..${path.sep}`) ||
        path.isAbsolute(relative)
      ) {
        return undefined;
      }
      return path.join(workspaceRoot, relative);
    }

    function resolveFromWorkspace(
      moduleName,
      containingFile,
      options,
      redirectedReference,
      resolutionMode,
    ) {
      if (
        moduleName.startsWith(".") ||
        path.isAbsolute(moduleName) ||
        /^[A-Za-z][A-Za-z\d+.-]*:/.test(moduleName)
      ) {
        return undefined;
      }
      const projectedFile = projectedContainingFile(containingFile);
      if (!projectedFile) {
        return undefined;
      }
      const result = ts.resolveModuleName(
        moduleName,
        projectedFile,
        options,
        host,
        resolutionCache,
        redirectedReference,
        resolutionMode,
      );
      return result.resolvedModule ? result : undefined;
    }

    host.resolveModuleNameLiterals = (
      moduleLiterals,
      containingFile,
      redirectedReference,
      options,
      containingSourceFile,
      reusedNames,
    ) => {
      const originalResults = originalResolve
        ? originalResolve(
            moduleLiterals,
            containingFile,
            redirectedReference,
            options,
            containingSourceFile,
            reusedNames,
          )
        : moduleLiterals.map((literal) =>
            ts.resolveModuleName(
              literal.text,
              containingFile,
              options,
              host,
              resolutionCache,
              redirectedReference,
              ts.getModeForUsageLocation(containingSourceFile, literal, options),
            ),
          );
      return originalResults.map((result, index) => {
        if (result?.resolvedModule) {
          return result;
        }
        const literal = moduleLiterals[index];
        return (
          resolveFromWorkspace(
            literal.text,
            containingFile,
            options,
            redirectedReference,
            ts.getModeForUsageLocation(containingSourceFile, literal, options),
          ) || result
        );
      });
    };

    host.getResolvedModuleWithFailedLookupLocationsFromCache = (
      moduleName,
      containingFile,
      resolutionMode,
    ) => {
      const originalResult = originalCachedResolve?.(
        moduleName,
        containingFile,
        resolutionMode,
      );
      if (originalResult?.resolvedModule) {
        return originalResult;
      }
      return (
        resolveFromWorkspace(
          moduleName,
          containingFile,
          compilerOptions,
          undefined,
          resolutionMode,
        ) || originalResult
      );
    };

    return info.languageService;
  }

  return { create };
}

module.exports = init;
