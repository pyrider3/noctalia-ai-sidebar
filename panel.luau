--!nonstrict
-- AI Sidebar Full-Height Panel for Noctalia & Niri
-- Supports API, Ollama, agy, and Codex backends with streaming, selection, and screenshot capture.

local current_backend = "agy"
local draft = ""
local composer_seq = 0
local attached_image = ""
local session = { messages = {}, status = "idle", error = "" }
local is_streaming = false
local anim_tick = 0
local LOADER_GLYPHS = { "loader", "loader-2", "loader-quarter" }

local function getPluginDir()
    local dir = noctalia.pluginDir() or "~/.config/noctalia/plugins/ai-sidebar"
    return noctalia.expandPath(dir)
end

local function getEngineScript()
    return getPluginDir() .. "/ai_engine.py"
end

local function getSessionFilePath()
    if noctalia.pluginDataDir then
        local dataDir = noctalia.pluginDataDir()
        if dataDir and dataDir ~= "" then
            return dataDir .. "/session.json"
        end
    end
    return noctalia.expandPath("~/.local/state/noctalia/plugins/data/pyrider3/ai-sidebar/session.json")
end

local function getBackendDisplayName(backend)
    if backend == "agy" then
        return "Antigravity (agy)"
    elseif backend == "codex" then
        return "Codex CLI"
    elseif backend == "api" then
        return "OpenAI / DeepSeek"
    elseif backend == "ollama" then
        return "本地 Ollama"
    else
        return string.upper(backend or "AI")
    end
end

local function syncConfigFromNoctalia()
    if not noctalia.getConfig then return end
    local cfg = {
        backend = noctalia.getConfig("default_backend") or "agy",
        api_url = noctalia.getConfig("api_url") or "https://api.deepseek.com/v1",
        api_key = noctalia.getConfig("api_key") or "",
        api_model = noctalia.getConfig("api_model") or "deepseek-chat",
        ollama_url = noctalia.getConfig("ollama_url") or "http://127.0.0.1:11434",
        ollama_model = noctalia.getConfig("ollama_model") or "llama3.2",
        system_prompt = noctalia.getConfig("system_prompt") or "You are a helpful, concise AI coding assistant in a Linux desktop environment."
    }
    local encoded = noctalia.json.encode(cfg)
    if encoded then
        local safe = encoded:gsub("'", "'\\''")
        noctalia.runAsync("python3 '" .. getEngineScript() .. "' save-config '" .. safe .. "'", nil, 3000)
    end
end

local function reloadSession()
    syncConfigFromNoctalia()
    local raw = noctalia.readFile(getSessionFilePath())
    if raw then
        local data = noctalia.json.decode(raw)
        if type(data) == "table" then
            session = data
            if data.active_backend and data.active_backend ~= "" then
                current_backend = data.active_backend
            end
            is_streaming = (data.status == "streaming")
        end
    end
end

local render

local function sendPrompt(textToSend)
    local query = textToSend or draft
    if not query or query == "" then
        return
    end

    local imgArg = attached_image or ""
    draft = ""
    attached_image = ""
    composer_seq = composer_seq + 1
    is_streaming = true

    -- Escape single quotes for bash safe argument passing
    local safeBackend = current_backend:gsub("'", "'\\''")
    local safePrompt = query:gsub("'", "'\\''")
    local safeImg = imgArg:gsub("'", "'\\''")

    local cmd = "python3 '" .. getEngineScript() .. "' send '" .. safeBackend .. "' '" .. safePrompt .. "' '" .. safeImg .. "'"
    noctalia.runAsync(cmd, function()
        reloadSession()
        render()
    end, 10000)

    render()
end

function onSendClicked()
    if is_streaming then
        return
    end
    sendPrompt(draft)
end

function onStopClicked()
    local cmd = "python3 '" .. getEngineScript() .. "' stop"
    noctalia.runAsync(cmd, function()
        reloadSession()
        render()
    end, 5000)
end

function onNewChatClicked()
    local cmd = "python3 '" .. getEngineScript() .. "' new-chat"
    noctalia.runAsync(cmd, function()
        reloadSession()
        attached_image = ""
        draft = ""
        composer_seq = composer_seq + 1
        render()
    end, 5000)
end

function onGrabSelectionClicked()
    local cmd = "python3 '" .. getEngineScript() .. "' capture-selection"
    noctalia.runAsync(cmd, function(res)
        local text = res.stdout or ""
        text = text:gsub("^%s+", ""):gsub("%s+$", "")
        if text ~= "" then
            if draft == "" then
                draft = text
            else
                draft = draft .. "\n\n" .. text
            end
            composer_seq = composer_seq + 1
            noctalia.notify("AI 侧边栏", "已读取屏幕划词文本")
            render()
        else
            noctalia.notify("AI 侧边栏", "未读取到划词内容，请先在任意窗口选中文字")
        end
    end, 3000)
end

function onScreenshotClicked()
    panel.close()
    local cmd = "python3 '" .. getEngineScript() .. "' capture-screen"
    noctalia.runAsync(cmd, function(res)
        local path = res.stdout or ""
        path = path:gsub("^%s+", ""):gsub("%s+$", "")
        noctalia.togglePanel("pyrider3/ai-sidebar:ai-sidebar-panel")
        if path ~= "" and noctalia.fileExists(path) then
            attached_image = path
            noctalia.notify("AI 侧边栏", "截图已就绪，请输入您对该图片的问题")
            render()
        end
    end, 20000)
end

function onCopyText(content)
    if not content or content == "" then return end
    local safe = content:gsub("'", "'\\''")
    local cmd = "printf '%s' '" .. safe .. "' | wl-copy"
    noctalia.runAsync(cmd, function()
        noctalia.notify("AI 侧边栏", "已复制回答内容到剪贴板")
    end, 2000)
end

function onCloseClicked()
    panel.close()
end

function onKey(chord, pressed)
    if not pressed then return end
    if chord == "Escape" then
        panel.close()
    end
end

render = function()
    local messageCards = {}

    if not session.messages or #session.messages == 0 then
        -- 初始空白引导卡片
        table.insert(messageCards, ui.column({
            align = "center",
            justify = "center",
            gap = 16,
            padding = 40,
            fill = "surface_variant/0.2",
            radius = 20,
        }, {
            ui.glyph({ name = "sparkles", size = 52, color = "primary" }),
            ui.label({ text = "AI 智能助手就绪", fontSize = 17, fontWeight = "bold", color = "on_surface" }),
            ui.label({
                text = "• 划词后点击「填入划词」一键送入输入框\n• 点击「区域截屏」框选屏幕图片并多模态识图\n• 点击顶部标签秒级切换后端引擎\n• 按 Super+S 随时呼出与收起侧边栏",
                textAlign = "left",
                fontSize = 13,
                color = "on_surface_variant",
            }),
            ui.row({ align = "center", gap = 8 }, {
                ui.button({
                    text = "解释代码",
                    variant = "secondary",
                    controlSize = "sm",
                    onClick = function()
                        sendPrompt("请详细解释以下代码的逻辑、设计思路及关键语法：")
                    end,
                }),
                ui.button({
                    text = "查找并修复 Bug",
                    variant = "secondary",
                    controlSize = "sm",
                    onClick = function()
                        sendPrompt("请分析以下内容中潜在的 Bug、语法错误或性能瓶颈，并给出修复方案：")
                    end,
                }),
                ui.button({
                    text = "翻译为中文",
                    variant = "secondary",
                    controlSize = "sm",
                    onClick = function()
                        sendPrompt("请将以下文本翻译为流畅、准确、符合技术语境的中文：")
                    end,
                }),
            }),
        }))
    else
        for idx, msg in ipairs(session.messages) do
            local role = msg.role
            local content = msg.content or ""
            local thinking = msg.thinking or ""
            local image = msg.image or ""
            local timeStr = msg.time or ""

            if role == "user" then
                -- 用户提问卡片
                local userChildren = {}
                if image ~= "" and noctalia.fileExists(image) then
                    table.insert(userChildren, ui.image({
                        path = image,
                        width = 160,
                        height = 100,
                        radius = 8,
                        fit = "cover",
                    }))
                end
                table.insert(userChildren, ui.label({
                    text = content,
                    fontSize = 13,
                    color = "on_surface",
                    selectable = true,
                }))
                table.insert(userChildren, ui.row({ align = "center", justify = "flex_end" }, {
                    ui.label({ text = timeStr, fontSize = 10, color = "on_surface_variant/0.7" }),
                }))

                table.insert(messageCards, ui.row({ justify = "flex_end" }, {
                    ui.column({
                        maxWidth = 420,
                        gap = 6,
                        padding = 12,
                        fill = "primary/0.18",
                        radius = 14,
                        border = "primary/0.3",
                        borderWidth = 1,
                    }, userChildren),
                }))

            elseif role == "assistant" then
                -- AI 回复卡片
                local assistantChildren = {}

                -- 头部信息栏
                local backendTag = msg.backend or current_backend
                table.insert(assistantChildren, ui.row({ align = "center", justify = "space_between" }, {
                    ui.row({ align = "center", gap = 6 }, {
                        ui.glyph({ name = "sparkles", size = 16, color = "primary" }),
                        ui.label({
                            text = getBackendDisplayName(backendTag),
                            fontSize = 11,
                            fontWeight = "bold",
                            color = "primary",
                        }),
                    }),
                    ui.label({ text = timeStr, fontSize = 10, color = "on_surface_variant/0.7" }),
                }))

                -- 深度思考折叠区（如果存在 thinking 文本）
                if thinking ~= "" then
                    table.insert(assistantChildren, ui.column({
                        padding = 10,
                        gap = 4,
                        radius = 10,
                        fill = "surface_variant/0.35",
                        border = "outline/0.2",
                        borderWidth = 1,
                    }, {
                        ui.row({ align = "center", gap = 6 }, {
                            ui.glyph({ name = "brain", size = 14, color = "secondary" }),
                            ui.label({ text = "深度思考过程", fontSize = 11, fontWeight = "semibold", color = "secondary" }),
                        }),
                        ui.label({
                            text = thinking,
                            fontSize = 11,
                            color = "on_surface_variant",
                            selectable = true,
                        }),
                    }))
                end

                -- 正文回答
                if content ~= "" then
                    table.insert(assistantChildren, ui.markdown({
                        text = content,
                        width = 440,
                    }))
                elseif is_streaming and idx == #session.messages then
                    -- 正在等待生成时的呼吸动效
                    local loaderIcon = LOADER_GLYPHS[(anim_tick % #LOADER_GLYPHS) + 1]
                    table.insert(assistantChildren, ui.row({ align = "center", gap = 8, padding = 8 }, {
                        ui.glyph({ name = loaderIcon, size = 18, color = "primary" }),
                        ui.label({ text = "正在生成回答中...", fontSize = 12, color = "on_surface_variant" }),
                    }))
                end

                -- 底部工具动作（复制）
                if content ~= "" then
                    table.insert(assistantChildren, ui.row({ align = "center", justify = "flex_end", gap = 6 }, {
                        ui.button({
                            glyph = "copy",
                            text = "复制回答",
                            variant = "ghost",
                            controlSize = "sm",
                            onClick = function()
                                onCopyText(content)
                            end,
                        }),
                    }))
                end

                table.insert(messageCards, ui.row({ justify = "flex_start" }, {
                    ui.column({
                        maxWidth = 480,
                        gap = 10,
                        padding = 14,
                        fill = "surface_variant/0.3",
                        radius = 16,
                        border = "outline/0.15",
                        borderWidth = 1,
                    }, assistantChildren),
                }))
            end
        end
    end

    -- 侧边栏整体布局
    panel.render(ui.column({ flexGrow = 1, gap = 12, padding = 16 }, {
        -- 顶部栏：标题、模型切换、快速清空与关闭
        ui.row({ align = "center", justify = "space_between", gap = 8 }, {
            ui.row({ align = "center", gap = 8 }, {
                ui.glyph({ name = "sparkles", size = 22, color = "primary" }),
                ui.label({ text = "AI 智能助手", fontSize = 16, fontWeight = "bold", color = "on_surface" }),
            }),
            ui.row({ align = "center", gap = 6 }, {
                ui.button({
                    glyph = "plus",
                    tooltip = "开启新对话",
                    variant = "ghost",
                    onClick = "onNewChatClicked",
                }),
                ui.button({
                    glyph = "close",
                    tooltip = "关闭侧边栏 (Super+S)",
                    variant = "ghost",
                    onClick = "onCloseClicked",
                }),
            }),
        }),

        -- 后端切换药丸组 (Tabs)
        ui.row({ align = "center", gap = 6 }, {
            ui.button({
                text = "agy (DeepMind)",
                controlSize = "sm",
                variant = (current_backend == "agy") and "primary" or "secondary",
                onClick = function()
                    current_backend = "agy"
                    render()
                end,
            }),
            ui.button({
                text = "Codex",
                controlSize = "sm",
                variant = (current_backend == "codex") and "primary" or "secondary",
                onClick = function()
                    current_backend = "codex"
                    render()
                end,
            }),
            ui.button({
                text = "API",
                controlSize = "sm",
                variant = (current_backend == "api") and "primary" or "secondary",
                onClick = function()
                    current_backend = "api"
                    render()
                end,
            }),
            ui.button({
                text = "Ollama",
                controlSize = "sm",
                variant = (current_backend == "ollama") and "primary" or "secondary",
                onClick = function()
                    current_backend = "ollama"
                    render()
                end,
            }),
        }),

        -- 快捷上下文条 (Context Bar)
        ui.row({ align = "center", gap = 8 }, {
            ui.button({
                glyph = "clipboard",
                text = "填入划词",
                variant = "secondary",
                controlSize = "sm",
                flexGrow = 1,
                tooltip = "读取当前选中的高亮文字并填入输入框",
                onClick = "onGrabSelectionClicked",
            }),
            ui.button({
                glyph = "camera",
                text = "区域截屏",
                variant = "secondary",
                controlSize = "sm",
                flexGrow = 1,
                tooltip = "选取屏幕区域进行多模态截图提问",
                onClick = "onScreenshotClicked",
            }),
        }),

        -- 附加截图预览条（如果已有选区截图）
        attached_image ~= "" and ui.row({
            align = "center",
            justify = "space_between",
            padding = 8,
            radius = 10,
            fill = "primary/0.15",
        }, {
            ui.row({ align = "center", gap = 10 }, {
                ui.image({
                    path = attached_image,
                    width = 60,
                    height = 42,
                    radius = 6,
                    fit = "cover",
                }),
                ui.label({ text = "已附加屏幕截图", fontSize = 12, fontWeight = "semibold", color = "primary" }),
            }),
            ui.button({
                glyph = "close",
                variant = "ghost",
                controlSize = "sm",
                onClick = function()
                    attached_image = ""
                    render()
                end,
            }),
        }) or ui.separator({ orientation = "horizontal", color = "outline/0.15" }),

        -- 对话消息流滚动区
        ui.scroll({ flexGrow = 1, gap = 12 }, messageCards),

        ui.separator({ orientation = "horizontal", color = "outline/0.15" }),

        -- 底部输入区 (Composer)
        ui.row({ align = "flex_end", gap = 8 }, {
            ui.input({
                key = "composer_" .. tostring(composer_seq),
                value = draft,
                placeholder = "输入问题... (Enter 发送, Shift+Enter 换行)",
                multiline = true,
                submitOnEnter = true,
                flexGrow = 1,
                onChange = function(text)
                    draft = text or ""
                end,
                onSubmit = function()
                    if not is_streaming then
                        onSendClicked()
                    end
                end,
            }),

            is_streaming and ui.button({
                glyph = "square",
                text = "停止",
                variant = "destructive",
                onClick = "onStopClicked",
            }) or ui.button({
                glyph = "send",
                text = "发送",
                variant = "primary",
                onClick = "onSendClicked",
            }),
        }),

        -- 底部小提示
        ui.row({ align = "center", justify = "space_between" }, {
            ui.label({
                text = "当前引擎: " .. getBackendDisplayName(current_backend) .. " • 按 Super+S 随时收起",
                fontSize = 11,
                color = "on_surface_variant/0.8",
            }),
            ui.label({
                text = "Enter 发送",
                fontSize = 11,
                color = "on_surface_variant/0.8",
            }),
        }),
    }))
end

function onOpen(_context)
    reloadSession()
    render()
end

function update()
    if is_streaming then
        anim_tick = anim_tick + 1
        reloadSession()
        render()
    end
end

noctalia.setUpdateInterval(200)
reloadSession()
