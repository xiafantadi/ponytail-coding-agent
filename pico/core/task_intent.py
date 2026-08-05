"""Small task-contract signals used by the final readiness gate."""

_EXPLICIT_WRITE_TOOLS = ("write_file", "patch_file", "delete_file", "move_file")
_READ_ONLY_MARKERS = (
    "without changing",
    "without modifying",
    "只读",
    "仅查看",
    "只检查",
)
_HARD_READ_ONLY_MARKERS = ("read-only", "do not modify files", "do not modify the workspace", "do not change files", "do not write files", "do not edit files")
_NON_WORKSPACE_CHANGE_MARKERS = ("# dream:", "memory consolidation", "memory directory:")
_CHANGE_MARKERS = (
    "fix",
    "modify",
    "implement",
    "refactor",
    "修复",
    "修改",
    "改动",
    "实现",
    "重构",
)
_WORKSPACE_ACTION_MARKERS = (
    "create file",
    "create a file",
    "write file",
    "add file",
    "remove file",
    "delete file",
    "update file",
    "编写代码",
    "写代码",
    "生成文件",
    "创建文件",
    "新增文件",
    "删除文件",
    "更新文件",
)


def request_requires_workspace_change(request):
    """Recognize explicit write intent without treating read-only requests as edits."""
    text = str(request or "").lower()
    if any(marker in text for marker in _NON_WORKSPACE_CHANGE_MARKERS):
        return False
    if any(marker in text for marker in _HARD_READ_ONLY_MARKERS):
        return False
    if any(marker in text for marker in _EXPLICIT_WRITE_TOOLS):
        return True
    if any(marker in text for marker in (*_CHANGE_MARKERS, *_WORKSPACE_ACTION_MARKERS)):
        return True
    if any(marker in text for marker in _READ_ONLY_MARKERS):
        return False
    return " change " in f" {text} "
