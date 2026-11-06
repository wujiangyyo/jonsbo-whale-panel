/**
 * dsh-panel-bridge —— 宿主侧（Node）。
 *
 * 本插件没有宿主逻辑：所有工作在浏览器侧完成（观察 DOM → POST 到副屏 API）。
 * 保留空 apply 以满足 DSH 插件契约。
 */
export function apply() {}
