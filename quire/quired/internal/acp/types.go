// Package acp holds the subset of the Agent Client Protocol (https://agentclientprotocol.com)
// that quired speaks, and a JSON-RPC 2.0 connection to carry it.
//
// ACP is the protocol between a client (an editor; for us, Quire) and a coding agent. quired is a
// client towards agents and, through the adapters in package harness, makes agents that don't
// speak ACP look as if they did. Session updates are kept as raw JSON so that fields this package
// doesn't model pass through unchanged.
package acp

import "encoding/json"

// ProtocolVersion is the ACP major version quired implements.
const ProtocolVersion = 1

// Methods the client calls on the agent.
const (
	MethodInitialize   = "initialize"
	MethodAuthenticate = "authenticate"
	MethodSessionNew   = "session/new"
	MethodSessionLoad  = "session/load"
	MethodPrompt       = "session/prompt"
	MethodCancel       = "session/cancel" // notification
)

// Methods the agent calls on the client.
const (
	MethodSessionUpdate     = "session/update" // notification
	MethodRequestPermission = "session/request_permission"
	MethodReadTextFile      = "fs/read_text_file"
	MethodWriteTextFile     = "fs/write_text_file"
)

// Stop reasons a prompt turn ends with.
const (
	StopEndTurn         = "end_turn"
	StopMaxTokens       = "max_tokens"
	StopMaxTurnRequests = "max_turn_requests"
	StopRefusal         = "refusal"
	StopCancelled       = "cancelled"
)

// Session update kinds (the "sessionUpdate" discriminator).
const (
	UpdateAgentMessageChunk = "agent_message_chunk"
	UpdateAgentThoughtChunk = "agent_thought_chunk"
	UpdateUserMessageChunk  = "user_message_chunk"
	UpdateToolCall          = "tool_call"
	UpdateToolCallUpdate    = "tool_call_update"
	UpdatePlan              = "plan"
	UpdateUsage             = "usage_update"
)

// Tool call kinds and statuses.
const (
	KindRead    = "read"
	KindEdit    = "edit"
	KindDelete  = "delete"
	KindMove    = "move"
	KindSearch  = "search"
	KindExecute = "execute"
	KindThink   = "think"
	KindFetch   = "fetch"
	KindOther   = "other"

	StatusPending    = "pending"
	StatusInProgress = "in_progress"
	StatusCompleted  = "completed"
	StatusFailed     = "failed"
)

// Permission option kinds and outcomes.
const (
	AllowOnce    = "allow_once"
	AllowAlways  = "allow_always"
	RejectOnce   = "reject_once"
	RejectAlways = "reject_always"

	OutcomeSelected  = "selected"
	OutcomeCancelled = "cancelled"
)

type Implementation struct {
	Name    string `json:"name"`
	Title   string `json:"title,omitempty"`
	Version string `json:"version,omitempty"`
}

type FileSystemCapability struct {
	ReadTextFile  bool `json:"readTextFile"`
	WriteTextFile bool `json:"writeTextFile"`
}

type ClientCapabilities struct {
	FS       FileSystemCapability `json:"fs"`
	Terminal bool                 `json:"terminal"`
}

type InitializeRequest struct {
	ProtocolVersion    int                `json:"protocolVersion"`
	ClientCapabilities ClientCapabilities `json:"clientCapabilities"`
	ClientInfo         *Implementation    `json:"clientInfo,omitempty"`
}

type PromptCapabilities struct {
	Image           bool `json:"image"`
	Audio           bool `json:"audio"`
	EmbeddedContext bool `json:"embeddedContext"`
}

type McpCapabilities struct {
	HTTP bool `json:"http"`
	SSE  bool `json:"sse"`
}

type AgentCapabilities struct {
	LoadSession        bool               `json:"loadSession"`
	PromptCapabilities PromptCapabilities `json:"promptCapabilities"`
	McpCapabilities    McpCapabilities    `json:"mcpCapabilities"`
}

type AuthMethod struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
}

type InitializeResponse struct {
	ProtocolVersion   int               `json:"protocolVersion"`
	AgentCapabilities AgentCapabilities `json:"agentCapabilities"`
	AuthMethods       []AuthMethod      `json:"authMethods"`
	AgentInfo         *Implementation   `json:"agentInfo,omitempty"`
}

type EnvVariable struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

// McpServer is the stdio form of an MCP server the client hands to the agent in session/new.
// Quire passes its OS tools to every agent this way.
type McpServer struct {
	Name    string        `json:"name"`
	Command string        `json:"command"`
	Args    []string      `json:"args"`
	Env     []EnvVariable `json:"env"`
}

type NewSessionRequest struct {
	Cwd        string      `json:"cwd"`
	McpServers []McpServer `json:"mcpServers"`
}

type NewSessionResponse struct {
	SessionID string          `json:"sessionId"`
	Modes     json.RawMessage `json:"modes,omitempty"`
	Models    json.RawMessage `json:"models,omitempty"`
}

// ContentBlock covers the text, image and resource_link blocks quired sends and renders.
type ContentBlock struct {
	Type     string `json:"type"`
	Text     string `json:"text,omitempty"`
	Data     string `json:"data,omitempty"`
	MimeType string `json:"mimeType,omitempty"`
	URI      string `json:"uri,omitempty"`
	Name     string `json:"name,omitempty"`
}

func TextBlock(s string) ContentBlock { return ContentBlock{Type: "text", Text: s} }

type PromptRequest struct {
	SessionID string         `json:"sessionId"`
	Prompt    []ContentBlock `json:"prompt"`
}

type PromptResponse struct {
	StopReason string `json:"stopReason"`
}

type CancelNotification struct {
	SessionID string `json:"sessionId"`
}

type SessionNotification struct {
	SessionID string          `json:"sessionId"`
	Update    json.RawMessage `json:"update"`
}

// SessionUpdate is the decoded view of one update. Content is raw because its shape depends on
// the kind: one ContentBlock for message chunks, a list of tool call contents for tool calls.
type SessionUpdate struct {
	Kind       string          `json:"sessionUpdate"`
	Content    json.RawMessage `json:"content,omitempty"`
	ToolCallID string          `json:"toolCallId,omitempty"`
	Title      string          `json:"title,omitempty"`
	ToolKind   string          `json:"kind,omitempty"`
	Status     string          `json:"status,omitempty"`
	RawInput   json.RawMessage `json:"rawInput,omitempty"`
	RawOutput  json.RawMessage `json:"rawOutput,omitempty"`
	Entries    []PlanEntry     `json:"entries,omitempty"`
	Used       *int64          `json:"used,omitempty"`
	Size       *int64          `json:"size,omitempty"`
}

type PlanEntry struct {
	Content  string `json:"content"`
	Priority string `json:"priority"`
	Status   string `json:"status"`
}

// ToolCallContent is one entry of a tool call's content list.
type ToolCallContent struct {
	Type    string        `json:"type"` // "content", "diff" or "terminal"
	Content *ContentBlock `json:"content,omitempty"`
	Path    string        `json:"path,omitempty"`
	OldText *string       `json:"oldText,omitempty"`
	NewText string        `json:"newText,omitempty"`
}

// ChunkText returns the text of a message or thought chunk, or "" for other updates.
func (u SessionUpdate) ChunkText() string {
	var b ContentBlock
	if len(u.Content) == 0 || json.Unmarshal(u.Content, &b) != nil {
		return ""
	}
	return b.Text
}

// Marshal encodes an update for SessionNotification.Update.
func (u SessionUpdate) Marshal() json.RawMessage {
	b, err := json.Marshal(u)
	if err != nil {
		panic(err) // every field is JSON-safe
	}
	return b
}

func ChunkUpdate(kind, text string) SessionUpdate {
	c, _ := json.Marshal(TextBlock(text))
	return SessionUpdate{Kind: kind, Content: c}
}

func ToolContent(blocks ...ToolCallContent) json.RawMessage {
	b, _ := json.Marshal(blocks)
	return b
}

type ToolCallRef struct {
	ToolCallID string          `json:"toolCallId"`
	Title      string          `json:"title,omitempty"`
	Kind       string          `json:"kind,omitempty"`
	Status     string          `json:"status,omitempty"`
	RawInput   json.RawMessage `json:"rawInput,omitempty"`
}

type PermissionOption struct {
	OptionID string `json:"optionId"`
	Name     string `json:"name"`
	Kind     string `json:"kind"`
}

type RequestPermissionRequest struct {
	SessionID string             `json:"sessionId"`
	ToolCall  ToolCallRef        `json:"toolCall"`
	Options   []PermissionOption `json:"options"`
}

type PermissionOutcome struct {
	Outcome  string `json:"outcome"`
	OptionID string `json:"optionId,omitempty"`
}

type RequestPermissionResponse struct {
	Outcome PermissionOutcome `json:"outcome"`
}

// Selected answers a permission request with one of its options.
func Selected(optionID string) RequestPermissionResponse {
	return RequestPermissionResponse{Outcome: PermissionOutcome{Outcome: OutcomeSelected, OptionID: optionID}}
}

// Cancelled answers a permission request when the turn was cancelled.
func Cancelled() RequestPermissionResponse {
	return RequestPermissionResponse{Outcome: PermissionOutcome{Outcome: OutcomeCancelled}}
}

type ReadTextFileRequest struct {
	SessionID string `json:"sessionId"`
	Path      string `json:"path"`
	Line      *int   `json:"line,omitempty"`
	Limit     *int   `json:"limit,omitempty"`
}

type ReadTextFileResponse struct {
	Content string `json:"content"`
}

type WriteTextFileRequest struct {
	SessionID string `json:"sessionId"`
	Path      string `json:"path"`
	Content   string `json:"content"`
}
