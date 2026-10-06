--!nonstrict
-- AI Sidebar Bar Widget for Noctalia

local PANEL_ID = "pyrider3/ai-sidebar:ai-sidebar-panel"
local is_generating = false
local anim_frame = 0
local ICONS = { "loader", "loader-2", "loader-quarter" }

local function getPluginDir()
    local dir = noctalia.pluginDir() or "~/.config/noctalia/plugins/ai-sidebar"
    return noctalia.expandPath(dir)
end

local function getSessionFile()
    if noctalia.pluginDataDir then
        local dataDir = noctalia.pluginDataDir()
        if dataDir and dataDir ~= "" then
            return dataDir .. "/session.json"
        end
    end
    return noctalia.expandPath("~/.local/state/noctalia/plugins/data/pyrider3/ai-sidebar/session.json")
end

local function render()
    if is_generating then
        anim_frame = (anim_frame % #ICONS) + 1
        barWidget.setGlyph(ICONS[anim_frame])
        barWidget.setColor("primary")
        barWidget.setText("AI")
        barWidget.setTooltip("AI 智能助手: 思考生成中...")
    else
        barWidget.setGlyph("sparkles")
        barWidget.setColor("on_surface")
        barWidget.setText("")
        barWidget.setTooltip("AI 智能助手 (点击或按 Super+S 呼出)")
    end
end

local function checkStatus()
    local raw = noctalia.readFile(getSessionFile())
    if raw then
        local data = noctalia.json.decode(raw)
        if type(data) == "table" and data.status == "streaming" then
            is_generating = true
        else
            is_generating = false
        end
    else
        is_generating = false
    end
    render()
end

function onClick()
    noctalia.togglePanel(PANEL_ID)
end

function update()
    checkStatus()
end

noctalia.setUpdateInterval(1000)
checkStatus()
