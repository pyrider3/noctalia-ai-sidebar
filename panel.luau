--!nonstrict
-- AI Sidebar — Modern Glassmorphism & Material 3 Expressive Panel for Noctalia & Niri
-- High-aesthetic chat interface with multi-backend streaming, selection grab, and multimodal screenshot.

local current_backend = "agy"
local draft = ""
local composer_seq = 0
local attached_image = ""
local session = { messages = {}, status = "idle", error = "" }
local is_streaming = false
local anim_tick = 0
local LOADER_GLYPHS = { "loader", "loader-2", "loader-quarter" }
local WRAP = 450

local BACKENDS = {
    { id = "agy", label = "⚡ agy", icon = "sparkles", desc = "Antigravity CLI" },
    { id = "codex", label = "💻 Codex", icon = "terminal", desc = "Codex CLI" },
    { id = "api", label = "🤖 API", icon = "cloud", desc = "DeepSeek / OpenAI" },
    { id = "ollama", label = "🦙 Ollama", icon = "cpu", desc = "本地私有模型" },
}

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

local function getBackendInfo(backendId)
    for _, b in ipairs(BACKENDS) do
        if b.id == backendId then
            return b
        end
    end
    return { id = backendId or "ai", label = string.upper(backendId or "AI"), icon = "sparkles", desc = "AI 引擎" }
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

-- 拆分 Markdown 与独立代码块，保证排版呼吸感与单独代码复制体验
local function split_markdown(txt)
    local segs = {}
    local in_code = false
    local lang = ""
    local buf = ""
    local function flush()
        if buf ~= "" then
            table.insert(segs, { code = in_code, lang = lang, text = buf })
            buf = ""
        end
    end
    for line in (txt .. "\n"):gmatch("([^\n]*)\n") do
        local stripped = line:match("^%s*(.*)$") or ""
        if stripped:sub(1, 3) == "```" then
            flush()
            if not in_code then
                lang = stripped:sub(4):match("^%s*(%w*)") or ""
            else
                lang = ""
            end
            in_code = not in_code
        else
            buf = buf .. line .. "\n"
        end
    end
    flush()
    return segs
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
    if is_streaming then return end
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
            noctalia.notify("AI 侧边栏", "已读取屏幕选中文本")
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
            noctalia.notify("AI 侧边栏", "屏幕截图已就绪，请输入针对该图片的问题")
            render()
        end
    end, 20000)
end

function onCopyText(content)
    if not content or content == "" then return end
    local safe = content:gsub("'", "'\\''")
    local cmd = "printf '%s' '" .. safe .. "' | wl-copy"
    noctalia.runAsync(cmd, function()
        noctalia.notify("AI 侧边栏", "已复制到剪贴板")
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
    local currentInfo = getBackendInfo(current_backend)

    if not session.messages or #session.messages == 0 then
        -- 🌟 极简高级空态引导区（Hero Greeting）
        table.insert(messageCards, ui.column({
            align = "center",
            justify = "center",
            gap = 14,
            padding = 24,
            flexGrow = 1,
        }, {
            -- 呼吸晶体图标
            ui.column({
                width = 56,
                height = 56,
                radius = 18,
                fill = "primary/0.18",
                align = "center",
                justify = "center",
            }, {
                ui.glyph({ name = "sparkles", size = 28, color = "primary" }),
            }),

            ui.column({ align = "center", gap = 4 }, {
                ui.label({ text = "今天有什么可以帮你？", fontSize = 17, fontWeight = "bold", color = "on_surface" }),
                ui.label({ text = "随时划词解析、框选屏幕或直接提问", fontSize = 12, color = "on_surface_variant" }),
            }),

            -- 快捷灵感药丸组（Prompt Chips）
            ui.column({ align = "center", gap = 8 }, {
                ui.row({ align = "center", gap = 8 }, {
                    ui.button({
                        text = "💡 解释选中文本",
                        variant = "secondary",
                        controlSize = "sm",
                        onClick = function()
                            onGrabSelectionClicked()
                        end,
                    }),
                    ui.button({
                        text = "🐛 排查代码 Bug",
                        variant = "secondary",
                        controlSize = "sm",
                        onClick = function()
                            sendPrompt("请帮我审查并排查这段代码中的潜在 Bug、边界情况或性能隐患：")
                        end,
                    }),
                }),
                ui.row({ align = "center", gap = 8 }, {
                    ui.button({
                        text = "🌐 润色为技术中文",
                        variant = "secondary",
                        controlSize = "sm",
                        onClick = function()
                            sendPrompt("请将以下内容润色翻译为自然、专业的技术中文：")
                        end,
                    }),
                    ui.button({
                        text = "📸 区域截屏分析",
                        variant = "secondary",
                        controlSize = "sm",
                        onClick = function()
                            onScreenshotClicked()
                        end,
                    }),
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
                -- 👤 用户发言气泡：右对齐、圆润胶囊
                local userContent = {}
                if image ~= "" and noctalia.fileExists(image) then
                    table.insert(userContent, ui.image({
                        path = image,
                        width = 180,
                        height = 110,
                        radius = 10,
                        fit = "cover",
                    }))
                end
                table.insert(userContent, ui.label({
                    text = content,
                    fontSize = 13,
                    color = "on_surface",
                    maxWidth = 400,
                    wrap = true,
                }))
                table.insert(userContent, ui.row({ align = "center", justify = "end" }, {
                    ui.label({ text = timeStr, fontSize = 10, color = "on_surface_variant" }),
                }))

                table.insert(messageCards, ui.row({ justify = "end" }, {
                    ui.column({
                        gap = 6,
                        padding = 12,
                        fill = "primary/0.25",
                        radius = 16,
                    }, userContent),
                }))

            elseif role == "assistant" then
                -- 🤖 AI 回复：开放式自然版面，通透高质感
                local assistantContent = {}
                local bInfo = getBackendInfo(msg.backend or current_backend)

                -- 头部身份标签与时间
                table.insert(assistantContent, ui.row({ align = "center", justify = "space_between" }, {
                    ui.row({ align = "center", gap = 6 }, {
                        ui.glyph({ name = bInfo.icon, size = 14, color = "primary" }),
                        ui.label({
                            text = bInfo.label,
                            fontSize = 12,
                            fontWeight = "bold",
                            color = "primary",
                        }),
                    }),
                    ui.label({ text = timeStr, fontSize = 10, color = "on_surface_variant" }),
                }))

                -- 深度思考折叠条（Thinking Process）
                if thinking ~= "" then
                    table.insert(assistantContent, ui.column({
                        padding = 10,
                        gap = 4,
                        radius = 10,
                        fill = "surface_variant/0.3",
                    }, {
                        ui.row({ align = "center", gap = 6 }, {
                            ui.glyph({ name = "brain", size = 13, color = "secondary" }),
                            ui.label({ text = "深度思考", fontSize = 11, fontWeight = "bold", color = "secondary" }),
                        }),
                        ui.label({
                            text = thinking,
                            fontSize = 11,
                            color = "on_surface_variant",
                            maxWidth = 440,
                            wrap = true,
                        }),
                    }))
                end

                -- 正文回答与代码块
                if content ~= "" then
                    local segs = split_markdown(content)
                    for _, seg in ipairs(segs) do
                        if seg.code then
                            local codeText = seg.text:gsub("\n+$", "")
                            table.insert(assistantContent, ui.column({
                                padding = 10,
                                radius = 10,
                                fill = "surface_variant/0.45",
                                gap = 6,
                            }, {
                                ui.row({ align = "center", justify = "space_between" }, {
                                    ui.label({
                                        text = (seg.lang ~= "" and string.upper(seg.lang) or "CODE"),
                                        fontSize = 10,
                                        fontWeight = "bold",
                                        color = "primary",
                                    }),
                                    ui.button({
                                        glyph = "copy",
                                        text = "复制代码",
                                        variant = "ghost",
                                        controlSize = "sm",
                                        onClick = function()
                                            onCopyText(codeText)
                                        end,
                                    }),
                                }),
                                ui.label({
                                    text = codeText,
                                    fontSize = 11,
                                    color = "on_surface",
                                    maxWidth = 440,
                                    wrap = true,
                                }),
                            }))
                        else
                            table.insert(assistantContent, ui.markdown({
                                text = seg.text,
                                width = WRAP,
                            }))
                        end
                    end
                elseif is_streaming and idx == #session.messages then
                    -- 正在生成中的优雅呼吸指示符
                    local loaderIcon = LOADER_GLYPHS[(anim_tick % #LOADER_GLYPHS) + 1]
                    table.insert(assistantContent, ui.row({ align = "center", gap = 8, padding = 4 }, {
                        ui.glyph({ name = loaderIcon, size = 16, color = "primary" }),
                        ui.label({ text = "思考并生成回答中...", fontSize = 12, color = "on_surface_variant" }),
                    }))
                end

                -- 底部工具栏
                if content ~= "" then
                    table.insert(assistantContent, ui.row({ align = "center", justify = "start", gap = 8 }, {
                        ui.button({
                            glyph = "copy",
                            text = "复制全文",
                            variant = "ghost",
                            controlSize = "sm",
                            onClick = function()
                                onCopyText(content)
                            end,
                        }),
                    }))
                end

                table.insert(messageCards, ui.row({ justify = "start" }, {
                    ui.column({
                        gap = 8,
                        padding = 12,
                        fill = "surface_variant/0.55",
                        radius = 16,
                    }, assistantContent),
                }))
            end
        end
    end

    -- 组装侧边栏主体元素列表（确保绝无 nil / 布尔值混入子节点）
    local bodyElements = {}

    -- 1. 顶部导航条（Header）：极简、通透、高质感
    table.insert(bodyElements, ui.row({ align = "center", justify = "space_between" }, {
        ui.row({ align = "center", gap = 8 }, {
            ui.glyph({ name = "sparkles", size = 20, color = "primary" }),
            ui.label({ text = "AI Copilot", fontSize = 16, fontWeight = "bold", color = "on_surface" }),
            ui.row({
                padding = 4,
                radius = 6,
                fill = "primary/0.15",
                align = "center",
            }, {
                ui.label({ text = currentInfo.label, fontSize = 10, fontWeight = "bold", color = "primary" }),
            }),
        }),
        ui.row({ align = "center", gap = 4 }, {
            ui.button({
                glyph = "plus",
                tooltip = "开启新对话",
                variant = "ghost",
                controlSize = "sm",
                onClick = "onNewChatClicked",
            }),
            ui.button({
                glyph = "trash",
                tooltip = "清空会话",
                variant = "ghost",
                controlSize = "sm",
                onClick = "onNewChatClicked",
            }),
            ui.button({
                glyph = "close",
                tooltip = "收起侧边栏 (Super+S / Esc)",
                variant = "ghost",
                controlSize = "sm",
                onClick = "onCloseClicked",
            }),
        }),
    }))

    -- 2. 极简紧凑引擎切换胶囊栏（Segmented Tabs）
    local tabButtons = {}
    for _, b in ipairs(BACKENDS) do
        table.insert(tabButtons, ui.button({
            text = b.label,
            controlSize = "sm",
            flexGrow = 1,
            variant = (current_backend == b.id) and "primary" or "ghost",
            onClick = function()
                current_backend = b.id
                render()
            end,
        }))
    end
    table.insert(bodyElements, ui.row({
        align = "center",
        padding = 4,
        radius = 12,
        fill = "surface_variant/0.25",
        gap = 4,
    }, tabButtons))

    -- 3. 消息滚动流
    table.insert(bodyElements, ui.scroll({ flexGrow = 1, gap = 12 }, messageCards))

    -- 4. 附加截图预览条（如果存在截图）
    if attached_image ~= "" and noctalia.fileExists(attached_image) then
        table.insert(bodyElements, ui.row({
            align = "center",
            justify = "space_between",
            padding = 6,
            radius = 10,
            fill = "primary/0.12",
        }, {
            ui.row({ align = "center", gap = 8 }, {
                ui.image({
                    path = attached_image,
                    width = 54,
                    height = 36,
                    radius = 6,
                    fit = "cover",
                }),
                ui.label({ text = "已加载屏幕区域截图", fontSize = 11, fontWeight = "bold", color = "primary" }),
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
        }))
    end

    -- 5. 底部悬浮输入卡片（Floating Composer Island）
    local composerActionBtn
    if is_streaming then
        composerActionBtn = ui.button({
            glyph = "square",
            text = "停止",
            variant = "destructive",
            controlSize = "sm",
            onClick = "onStopClicked",
        })
    else
        composerActionBtn = ui.button({
            glyph = "send",
            text = "发送",
            variant = "primary",
            controlSize = "sm",
            onClick = "onSendClicked",
        })
    end

    table.insert(bodyElements, ui.column({
        padding = 10,
        radius = 16,
        fill = "surface_variant/0.5",
        gap = 8,
    }, {
        -- 输入框
        ui.input({
            key = "composer_" .. tostring(composer_seq),
            value = draft,
            placeholder = "向 " .. currentInfo.label .. " 提问... (Enter 发送, Shift+Enter 换行)",
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

        -- 底部微型工具条
        ui.row({ align = "center", justify = "space_between" }, {
            ui.row({ align = "center", gap = 4 }, {
                ui.button({
                    glyph = "clipboard",
                    text = "划词填入",
                    variant = "ghost",
                    controlSize = "sm",
                    tooltip = "读取当前屏幕选中的文字",
                    onClick = "onGrabSelectionClicked",
                }),
                ui.button({
                    glyph = "camera",
                    text = "截屏提问",
                    variant = "ghost",
                    controlSize = "sm",
                    tooltip = "框选屏幕区域进行截图",
                    onClick = "onScreenshotClicked",
                }),
            }),
            composerActionBtn,
        }),
    }))

    -- 6. 极简底部微标
    table.insert(bodyElements, ui.row({ align = "center", justify = "center", padding = 4 }, {
        ui.label({
            text = "Super+S 呼出/收起 • Shift+Enter 换行 • Esc 关闭",
            fontSize = 11,
            color = "on_surface_variant",
        }),
    }))

    -- 侧边栏全屏抽屉容器
    panel.render(ui.column({
        flexGrow = 1,
        gap = 12,
        padding = 16,
        fill = "surface/0.92",
        radius = 20,
    }, bodyElements))
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
