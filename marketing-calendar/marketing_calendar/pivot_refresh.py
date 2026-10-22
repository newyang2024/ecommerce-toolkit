"""使用本机 Excel 原生透视表功能刷新输出副本中的汇总页。"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Callable


class PivotRefreshError(RuntimeError):
    """Excel 透视筛选或缓存刷新失败。"""


_POWERSHELL = r"""param(
    [Parameter(Mandatory = $true)][string]$workbookPath,
    [Parameter(Mandatory = $true)][string]$endDateText
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$endDate = [DateTime]::ParseExact($endDateText, 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture)
$latestName = '{0}/{1}/{2}' -f $endDate.Year, $endDate.Month, $endDate.Day

function Send-Progress([string]$phase, [int]$index, [int]$total) {
    [Console]::Out.WriteLine(('PROGRESS|{0}|{1}|{2}' -f $phase, $index, $total))
    [Console]::Out.Flush()
}

function Test-DateItems($field) {
    $items = $field.PivotItems()
    for ($index = 1; $index -le $items.Count; $index++) {
        if ([string]$items.Item($index).Name -match '^\d{4}/\d{1,2}/\d{1,2}$') { return $true }
    }
    return $false
}

function Get-DatePageField($pivot) {
    $matches = @()
    $fields = $pivot.PivotFields()
    for ($index = 1; $index -le $fields.Count; $index++) {
        $field = $fields.Item($index)
        if ($field.Orientation -ne 3) { continue }
        $name = [string]$field.Name
        if ($name.Trim() -eq '日期' -or ($name.Trim().Length -eq 0 -and (Test-DateItems $field))) {
            $matches += $field
        }
    }
    if ($matches.Count -ne 1) {
        throw "PivotTable '$($pivot.Name)' 的日期筛选字段不唯一或缺失，找到 $($matches.Count) 个。"
    }
    return $matches[0]
}

function Get-FilterSnapshot($field) {
    $multiple = [bool]$field.EnableMultiplePageItems
    if (-not $multiple) {
        $current = [string]$field.CurrentPage.Name
        return [pscustomobject]@{
            Multiple = $false
            SelectAll = $false
            Items = @($current)
        }
    }
    $selected = New-Object System.Collections.ArrayList
    $items = $field.PivotItems()
    for ($index = 1; $index -le $items.Count; $index++) {
        $item = $items.Item($index)
        if ($item.Visible) { [void]$selected.Add([string]$item.Name) }
    }
    if ($items.Count -eq 0) { throw "筛选字段 '$($field.Name)' 没有可见选项。" }
    $names = @($selected | Sort-Object -Unique)
    return [pscustomobject]@{
        Multiple = $true
        SelectAll = ($names.Count -eq $items.Count)
        Items = $names
    }
}

function Get-FilterSignature($snapshot) {
    if ($snapshot.SelectAll) { return 'MULTI|ALL' }
    $names = @($snapshot.Items | Sort-Object -Unique)
    return ('{0}|{1}' -f [bool]$snapshot.Multiple, ($names -join ';'))
}

function Restore-FilterSnapshot($field, $snapshot) {
    if ($snapshot.SelectAll) {
        $field.EnableMultiplePageItems = $true
        $items = $field.PivotItems()
        if ($items.Count -eq 0) { throw "筛选字段 '$($field.Name)' 刷新后没有可用项。" }
        for ($index = 1; $index -le $items.Count; $index++) {
            $items.Item($index).Visible = $true
        }
        return $snapshot
    }
    $available = New-Object System.Collections.ArrayList
    $missing = New-Object System.Collections.ArrayList
    $items = $field.PivotItems()
    foreach ($wantedName in $snapshot.Items) {
        $found = $false
        for ($index = 1; $index -le $items.Count; $index++) {
            if ([string]$items.Item($index).Name -eq [string]$wantedName) {
                $found = $true
                break
            }
        }
        if ($found) { [void]$available.Add([string]$wantedName) }
        else { [void]$missing.Add([string]$wantedName) }
    }
    if ($available.Count -eq 0) {
        throw "筛选字段 '$($field.Name)' 原选项在刷新后均不存在，无法安全保留：$($snapshot.Items -join ', ')。"
    }
    Set-PageItems $field ([string[]]$available.ToArray())
    if (-not $snapshot.Multiple) {
        if ($available.Count -ne 1) {
            throw "单选筛选字段 '$($field.Name)' 原状态不唯一。"
        }
        $field.EnableMultiplePageItems = $false
        $field.CurrentPage = [string]$available[0]
    }
    return [pscustomobject]@{
        Multiple = [bool]$snapshot.Multiple
        SelectAll = $false
        Items = @($available.ToArray())
        Missing = @($missing.ToArray())
    }
}

function Get-TargetNames([bool]$monthly) {
    if (-not $monthly) { return ,@($latestName) }
    $names = New-Object System.Collections.ArrayList
    $dateItems = $script:targetDateField.PivotItems()
    $pattern = '^([0-9]{4})/([0-9]{1,2})/([0-9]{1,2})$'
    $hasLatest = $false
    for ($index = 1; $index -le $dateItems.Count; $index++) {
        $name = [string]$dateItems.Item($index).Name
        if ($name -match $pattern) {
            $year = [int]$Matches[1]
            $month = [int]$Matches[2]
            $day = [int]$Matches[3]
            if ($year -eq $endDate.Year -and $month -eq $endDate.Month -and $day -le $endDate.Day) {
                if ($name -eq $latestName) { $hasLatest = $true }
                if (-not $names.Contains($name)) { [void]$names.Add($name) }
            }
        }
    }
    if (-not $hasLatest) { throw "月度日期筛选中找不到最新日 $latestName。" }
    return ,@($names.ToArray())
}

function Set-PageItems($field, [string[]]$wantedNames) {
    if ($wantedNames.Count -eq 0) { throw "筛选字段 '$($field.Name)' 没有目标项。" }
    $wanted = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($name in $wantedNames) { [void]$wanted.Add([string]$name) }
    $items = $field.PivotItems()
    $found = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $field.EnableMultiplePageItems = $true
    for ($index = 1; $index -le $items.Count; $index++) {
        $item = $items.Item($index)
        $name = [string]$item.Name
        if ($wanted.Contains($name)) {
            $item.Visible = $true
            [void]$found.Add($name)
        }
    }
    foreach ($name in $wanted) {
        if (-not $found.Contains($name)) { throw "筛选字段 '$($field.Name)' 中找不到目标项 '$name'。" }
    }
    for ($index = 1; $index -le $items.Count; $index++) {
        $item = $items.Item($index)
        if (-not $wanted.Contains([string]$item.Name)) { $item.Visible = $false }
    }
}

$excel = $null
$book = $null
$failed = $false
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $excel.EnableEvents = $false
    $excel.AutomationSecurity = 3
    $excel.ScreenUpdating = $false
    $book = $excel.Workbooks.Open($workbookPath, 0, $false)
    if ($book.ReadOnly) { throw '输出工作簿以只读方式打开，不能安全刷新。' }

    $stopIndex = $book.Worksheets.Item('超级短视频').Index
    $targets = New-Object System.Collections.ArrayList
    $cacheIndices = New-Object 'System.Collections.Generic.HashSet[int]'
    for ($sheetIndex = 1; $sheetIndex -lt $stopIndex; $sheetIndex++) {
        $sheet = $book.Worksheets.Item($sheetIndex)
        $pivots = $sheet.PivotTables()
        for ($pivotIndex = 1; $pivotIndex -le $pivots.Count; $pivotIndex++) {
            $pivot = $pivots.Item($pivotIndex)
            try {
                $dateField = Get-DatePageField $pivot
            } catch {
                throw "工作表 '$($sheet.Name)' 的透视表 '$($pivot.Name)' 日期字段检查失败：$($_.Exception.Message)"
            }
            $monthField = $null
            $monthly = $false
            if ($sheet.Name -eq '渠道') {
                try {
                    $candidate = $pivot.PivotFields('月份')
                    if ($candidate.Orientation -eq 3) { $monthField = $candidate; $monthly = $true }
                } catch { }
            }
            $filters = @{}
            $fields = $pivot.PivotFields()
            for ($fieldIndex = 1; $fieldIndex -le $fields.Count; $fieldIndex++) {
                $field = $fields.Item($fieldIndex)
                if ($field.Orientation -ne 3) { continue }
                if ([string]$field.Name -eq [string]$dateField.Name) { continue }
                if ($monthly -and [string]$field.Name -eq [string]$monthField.Name) { continue }
                $filters[[string]$field.Name] = Get-FilterSnapshot $field
            }
            [void]$targets.Add([pscustomobject]@{
                Sheet = $sheet
                Pivot = $pivot
                DateField = $dateField
                MonthField = $monthField
                Monthly = $monthly
                OtherFilters = $filters
            })
            [void]$cacheIndices.Add([int]$pivot.CacheIndex)
        }
    }
    $monthlyTargets = @($targets | Where-Object { $_.Monthly })
    if ($monthlyTargets.Count -ne 1) { throw "应有且只有一个‘渠道’月度透视表，实际 $($monthlyTargets.Count) 个。" }
    if ($targets.Count -eq 0) { throw '“超级短视频”之前没有找到可更新的汇总透视表。' }

    $caches = $book.PivotCaches()
    $cacheList = @($cacheIndices | Sort-Object)
    for ($index = 0; $index -lt $cacheList.Count; $index++) {
        $cache = $caches.Item([int]$cacheList[$index])
        if ($cache.SourceType -ne 1) { throw "透视缓存 $($cacheList[$index]) 不是本地工作表数据源，拒绝外部刷新。" }
        $cache.Refresh()
        Send-Progress 'CACHE' ($index + 1) $cacheList.Count
    }

    for ($index = 0; $index -lt $targets.Count; $index++) {
        $target = $targets[$index]
        $pivot = $target.Pivot
        $script:targetDateField = $target.DateField
        try {
            $pivot.ManualUpdate = $true
            $fields = $pivot.PivotFields()
            for ($fieldIndex = 1; $fieldIndex -le $fields.Count; $fieldIndex++) {
                $field = $fields.Item($fieldIndex)
                if ($field.Orientation -ne 3) { continue }
                $name = [string]$field.Name
                if (-not $target.OtherFilters.ContainsKey($name)) { continue }
                $original = $target.OtherFilters[$name]
                $restored = Restore-FilterSnapshot $field $original
                $target.OtherFilters[$name] = $restored
                if ($restored.Missing -and $restored.Missing.Count -gt 0) {
                    [Console]::Out.WriteLine((
                        "NOTICE|工作表 '$($target.Sheet.Name)' / 透视表 '$($pivot.Name)' / 筛选 '$name'：新数据中不存在的旧选项已忽略（$($restored.Missing -join ', ')）"
                    ))
                    [Console]::Out.Flush()
                }
            }
            if ($target.Monthly) {
                Set-PageItems $target.MonthField @([string]$endDate.Month)
                $monthDates = Get-TargetNames $true
                Set-PageItems $target.DateField $monthDates
            } else {
                Set-PageItems $target.DateField @($latestName)
            }
            $pivot.ManualUpdate = $false
            if (-not $pivot.RefreshTable()) { throw "透视表未能刷新。" }
        } catch {
            throw "工作表 '$($target.Sheet.Name)' 的透视表 '$($pivot.Name)' 刷新或筛选恢复失败：$($_.Exception.Message)"
        }

        $expectedDateNames = if ($target.Monthly) { @($monthDates | Sort-Object -Unique) } else { @($latestName) }
        $visibleDates = @()
        $items = $target.DateField.PivotItems()
        for ($itemIndex = 1; $itemIndex -le $items.Count; $itemIndex++) {
            $item = $items.Item($itemIndex)
            if ($item.Visible -and [string]$item.Name -match '^\d{4}/\d{1,2}/\d{1,2}$') { $visibleDates += [string]$item.Name }
        }
        if ((@($visibleDates | Sort-Object -Unique) -join ';') -ne ($expectedDateNames -join ';')) {
            throw "透视表 '$($pivot.Name)' 的日期筛选回读校验失败。"
        }
        if ($target.Monthly) {
            $visibleMonths = @()
            $monthItems = $target.MonthField.PivotItems()
            for ($itemIndex = 1; $itemIndex -le $monthItems.Count; $itemIndex++) {
                $item = $monthItems.Item($itemIndex)
                if ($item.Visible) { $visibleMonths += [string]$item.Name }
            }
            if ((@($visibleMonths | Sort-Object -Unique) -join ';') -ne [string]$endDate.Month) {
                throw "月度透视表 '$($pivot.Name)' 的月份筛选回读校验失败。"
            }
        }
        $fields = $pivot.PivotFields()
        for ($fieldIndex = 1; $fieldIndex -le $fields.Count; $fieldIndex++) {
            $field = $fields.Item($fieldIndex)
            if ($field.Orientation -ne 3) { continue }
            $name = [string]$field.Name
            if ($name -eq [string]$target.DateField.Name) { continue }
            if ($target.Monthly -and $name -eq [string]$target.MonthField.Name) { continue }
            if ($target.OtherFilters.ContainsKey($name)) {
                $actual = Get-FilterSnapshot $field
                if ((Get-FilterSignature $actual) -ne (Get-FilterSignature $target.OtherFilters[$name])) {
                    throw "工作表 '$($target.Sheet.Name)' 的透视表 '$($pivot.Name)' 非日期筛选 '$name' 恢复后仍不一致，拒绝发布。"
                }
            }
        }
        Send-Progress 'TABLE' ($index + 1) $targets.Count
    }

    $book.Save()
    [Console]::Out.WriteLine('SUCCESS')
    [Console]::Out.Flush()
} catch {
    [Console]::Out.WriteLine(('FAIL|' + $_.Exception.Message))
    [Console]::Out.Flush()
    $failed = $true
} finally {
    if ($book) { try { $book.Close($false) } catch { } }
    if ($excel) { try { $excel.Quit() } catch { } }
}
if ($failed) { exit 1 }
"""


def refresh_summary_pivots(
    workbook_path: Path,
    latest_date: date,
    *,
    progress: Callable[[int, str], None] | None = None,
) -> tuple[str, ...]:
    """刷新“超级短视频”之前的汇总透视表，仅改约定的日期筛选。"""
    executable = shutil.which("powershell.exe")
    if executable is None:
        raise PivotRefreshError("找不到 Windows PowerShell，无法刷新汇总透视表。")
    resolved_path = str(Path(workbook_path).resolve())
    script_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="marketing-calendar-pivot-", suffix=".ps1", delete=False
        ) as script_file:
            script_path = Path(script_file.name)
            script_file.write(b"\xef\xbb\xbf" + _POWERSHELL.encode("utf-8"))
        process = subprocess.Popen(
            [
                executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-STA",
                "-ExecutionPolicy", "Bypass", "-File", str(script_path),
                resolved_path, latest_date.isoformat(),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        if script_path is not None:
            script_path.unlink(missing_ok=True)
        raise PivotRefreshError(f"无法启动 Windows Excel 透视刷新：{exc}") from exc
    output: list[str] = []
    failure: str | None = None
    notices: list[str] = []
    last_percent = 68
    if process.stdout is not None:
        for line in process.stdout:
            text = line.strip()
            if text.startswith("PROGRESS|"):
                _, phase, current_text, total_text = text.split("|", 3)
                current, total = int(current_text), max(1, int(total_text))
                if progress is not None:
                    if phase == "CACHE":
                        percent = 68 + int(current * 10 / total)
                        message = f"刷新透视缓存 {current}/{total}"
                    else:
                        percent = 78 + int(current * 19 / total)
                        message = f"更新日期筛选并刷新汇总表 {current}/{total}"
                    last_percent = percent
                    progress(percent, message)
            elif text.startswith("FAIL|"):
                failure = text[5:]
            elif text.startswith("NOTICE|"):
                notices.append(text[7:])
                if progress is not None:
                    progress(last_percent, text[7:])
            elif text:
                output.append(text)
    return_code = process.wait()
    if script_path is not None:
        script_path.unlink(missing_ok=True)
    if return_code != 0 or "SUCCESS" not in output:
        details = failure or "\n".join(output[-8:]) or f"PowerShell exit code {return_code}"
        raise PivotRefreshError(f"Excel 汇总透视刷新失败，未发布新工作簿：{details}")
    return tuple(notices)
