param(
    [ValidateSet("Host", "Compose")]
    [string]$Mode = "Host"
)

$ErrorActionPreference = "Stop"
$ChatModel = if ($env:LOCAL_CHAT_MODEL) { $env:LOCAL_CHAT_MODEL } else { "qwen2.5:3b" }
$EmbedModel = if ($env:LOCAL_EMBEDDING_MODEL) { $env:LOCAL_EMBEDDING_MODEL } else { "nomic-embed-text" }
$BaseUrl = if ($env:LOCAL_AI_BASE_URL) { $env:LOCAL_AI_BASE_URL.TrimEnd('/') } else { "http://127.0.0.1:11434" }

if ($Mode -eq "Compose") {
    docker compose up -d ollama
    docker compose run --rm ollama-model-init
    $BaseUrl = "http://127.0.0.1:11434"
} else {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        throw "Ollama is not installed. Install it from the approved package source first."
    }
    Invoke-RestMethod -Uri "$BaseUrl/api/tags" | Out-Null
    ollama pull $ChatModel
    ollama pull $EmbedModel
}

$Tags = Invoke-RestMethod -Uri "$BaseUrl/api/tags"
$Installed = @($Tags.models | ForEach-Object { $_.name -replace ':latest$', '' })
foreach ($Model in @($ChatModel, $EmbedModel)) {
    if ($Installed -notcontains $Model) { throw "Required model is missing: $Model" }
}

Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/embed" -ContentType "application/json" `
    -Body (@{ model = $EmbedModel; input = @("WorkMate embedding smoke test") } | ConvertTo-Json) | Out-Null
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/chat" -ContentType "application/json" `
    -Body (@{ model = $ChatModel; stream = $false; format = "json"; messages = @(@{ role = "user"; content = 'Return {"answer":"OK","source_ids":[]}' }) } | ConvertTo-Json -Depth 5) | Out-Null

Write-Host "Local chat and embedding models are installed and responding."
