# Interfaces Specification

> Extracted from Go source code. These are the port contracts for the Python rewrite.

---

## Datastore
**File:** `server/datastore.go`
**Implemented by:** `filedatastore` (server/modules/filedatastore)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| CreateNode | ctx context.Context, id string | *model.Node | Create a new Node with the given ID |
| GetNodes | ctx context.Context | []*model.Node | Retrieve all registered nodes |
| AddNode | ctx context.Context, node *model.Node | error | Add a node to the datastore |
| UpdateNode | ctx context.Context, newNode *model.Node | (*model.Node, error) | Update an existing node, return updated copy |
| GetNextJob | ctx context.Context, nodeId string | *model.Job | Get the next pending job for a given node |
| CreateJob | ctx context.Context | *model.Job | Create a new empty Job |
| GetJob | ctx context.Context, jobId int | *model.Job | Get a job by its integer ID |
| GetJobs | ctx context.Context, kind string, parameters map[string]interface{} | []*model.Job | Get jobs filtered by kind and parameters |
| AddJob | ctx context.Context, job *model.Job | error | Add a job to the datastore |
| AddPivotJob | ctx context.Context, job *model.Job | error | Add a pivot job to the datastore |
| UpdateJob | ctx context.Context, job *model.Job | error | Update an existing job |
| DeleteJob | ctx context.Context, jobId int | (*model.Job, error) | Delete a job by ID, return the deleted job |
| GetPackets | ctx context.Context, jobId int, offset int, count int, unwrap bool | ([]*model.Packet, error) | Get packets for a job with pagination and optional unwrap |
| SaveJobStream | ctx context.Context, jobId int, reader io.ReadCloser | error | Save a PCAP/stream for a job from a reader |
| GetJobStream | ctx context.Context, jobId int, unwrap bool | (io.ReadCloser, string, int64, string, error) | Get stream for a job; returns reader, filename, size, MIME type |

---

## Userstore
**File:** `server/userstore.go`
**Implemented by:** `kratos` (server/modules/kratos)

> Read-only interface into the auth system. Writes go through AdminUserstore.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| GetUsers | ctx context.Context | ([]*model.User, error) | Get all users |
| GetUserById | ctx context.Context, id string | (*model.User, error) | Get a single user by ID |

---

## AdminUserstore
**File:** `server/adminuserstore.go`
**Implemented by:** `salt` (server/modules/salt)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| AddUser | ctx context.Context, user *model.User | error | Create a new user |
| DeleteUser | ctx context.Context, id string | error | Delete a user by ID |
| UpdateProfile | ctx context.Context, user *model.User | error | Update a user's profile fields |
| ResetPassword | ctx context.Context, id string, password string | error | Reset a user's password |
| EnableUser | ctx context.Context, id string | error | Enable a disabled user |
| DisableUser | ctx context.Context, id string | error | Disable an active user |
| AddRole | ctx context.Context, id string, role string, bypassAuthCheck bool | error | Assign a role to a user; optionally bypass auth check |
| DeleteRole | ctx context.Context, id string, role string | error | Remove a role from a user |
| SyncUsers | ctx context.Context | error | Synchronize users with the upstream auth provider |

---

## Clientstore
**File:** `server/clientstore.go`
**Implemented by:** `hydra` (server/modules/hydra)

> Read-only interface into the auth system. Writes go through AdminClientstore.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| GetClients | ctx context.Context | ([]*model.Client, error) | Get all OAuth2 clients |
| GetClientByToken | ctx context.Context, token string | (*model.Client, error) | Look up a client by its bearer token |
| GetClientById | ctx context.Context, id string | (*model.Client, error) | Look up a client by its ID |

---

## AdminClientstore
**File:** `server/adminclientstore.go`
**Implemented by:** `salt` (server/modules/salt)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| AddClient | ctx context.Context, client *model.Client | (*model.Client, error) | Create a new OAuth2 client, return created copy |
| DeleteClient | ctx context.Context, id string | error | Delete a client by ID |
| GenerateSecret | ctx context.Context, id string | (*model.Client, error) | Regenerate the client secret; return updated client |
| UpdateClient | ctx context.Context, client *model.Client | error | Update client metadata |
| AddClientPermission | ctx context.Context, id string, perm string | error | Grant a permission to a client |
| DeleteClientPermission | ctx context.Context, id string, perm string | error | Revoke a permission from a client |

---

## Casestore
**File:** `server/casestore.go`
**Implemented by:** `elastic` (server/modules/elastic), `elasticcases` (server/modules/elasticcases), `httpcase` (server/modules/generichttp), `thehive` (server/modules/thehive)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| Create | ctx context.Context, newCase *model.Case | (*model.Case, error) | Create a new case |
| Update | ctx context.Context, socCase *model.Case | (*model.Case, error) | Update an existing case |
| GetCase | ctx context.Context, caseId string | (*model.Case, error) | Get a case by ID |
| GetCaseHistory | ctx context.Context, caseId string | ([]interface{}, error) | Get the audit history of a case |
| CreateComment | ctx context.Context, newComment *model.Comment | (*model.Comment, error) | Add a comment to a case |
| GetComment | ctx context.Context, commentId string | (*model.Comment, error) | Get a comment by ID |
| GetComments | ctx context.Context, caseId string | ([]*model.Comment, error) | Get all comments for a case |
| UpdateComment | ctx context.Context, comment *model.Comment | (*model.Comment, error) | Update an existing comment |
| DeleteComment | ctx context.Context, id string | error | Delete a comment by ID |
| CreateRelatedEvents | ctx context.Context, events []*model.RelatedEvent | (int, map[string]error, error) | Bulk-create related events; returns count, per-event errors, and overall error |
| GetRelatedEvent | ctx context.Context, id string | (*model.RelatedEvent, error) | Get a related event by ID |
| GetRelatedEvents | ctx context.Context, caseId string | ([]*model.RelatedEvent, error) | Get all related events for a case |
| DeleteRelatedEvent | ctx context.Context, id string | error | Delete a related event by ID |
| CreateArtifact | ctx context.Context, artifact *model.Artifact | (*model.Artifact, error) | Create a case artifact (observable) |
| GetArtifact | ctx context.Context, id string | (*model.Artifact, error) | Get an artifact by ID |
| GetArtifacts | ctx context.Context, caseId string, groupType string, groupId string | ([]*model.Artifact, error) | Get artifacts filtered by case, group type, and group ID |
| DeleteArtifact | ctx context.Context, id string | error | Delete an artifact by ID |
| UpdateArtifact | ctx context.Context, artifact *model.Artifact | (*model.Artifact, error) | Update an existing artifact |
| GetCaseIdsWithArtifact | ctx context.Context, artType string, value string | ([]string, error) | Find case IDs that contain a specific artifact value |
| CreateArtifactStream | ctx context.Context, artifactstream *model.ArtifactStream | (string, error) | Create a binary artifact stream; returns stream ID |
| GetArtifactStream | ctx context.Context, id string | (*model.ArtifactStream, error) | Get an artifact stream by ID |
| DeleteArtifactStream | ctx context.Context, id string | error | Delete an artifact stream by ID |
| BuildBulkIndexer | ctx context.Context, logger log.Interface | (esutil.BulkIndexer, error) | Build an Elasticsearch bulk indexer for batch operations |
| ConvertObjectToDocument | ctx context.Context, kind string, obj any, auditable *model.Auditable, isEdit bool, auditDocId *string, op *string | (doc []byte, index string, err error) | Serialize an object into an ES document with audit metadata |

---

## Eventstore
**File:** `server/eventstore.go`
**Implemented by:** `elastic` (server/modules/elastic)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| Search | ctx context.Context, criteria *model.EventSearchCriteria | (*model.EventSearchResults, error) | Execute an event search |
| MSearch | ctx context.Context, criteria []*model.EventMSearchCriteria | (*model.EventMSearchResults, error) | Execute a multi-search (multiple queries in one call) |
| Scroll | ctx context.Context, criteria *model.EventScrollCriteria, indexes []string | (*model.EventScrollResults, error) | Scroll through large result sets |
| Index | ctx context.Context, index string, document map[string]interface{}, id string | (*model.EventIndexResults, error) | Index (upsert) a document into the given index |
| Update | ctx context.Context, criteria *model.EventUpdateCriteria | (*model.EventUpdateResults, error) | Update events matching criteria |
| Delete | ctx context.Context, index string, id string | error | Delete a document by index and ID |
| Acknowledge | ctx context.Context, criteria *model.EventAckCriteria | (*model.EventUpdateResults, error) | Acknowledge (mark as reviewed) events matching criteria |
| GetActiveQueries | ctx context.Context, filter bool | ([]*model.QueryTask, error) | Get currently executing queries; optionally filter by user |
| CancelQuery | ctx context.Context, queryId string | error | Cancel a running query by ID |

---

## Detectionstore
**File:** `server/detectionstore.go`
**Implemented by:** `elastic` (server/modules/elastic)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| CreateDetection | ctx context.Context, detect *model.Detection | (*model.Detection, error) | Create a new detection |
| GetDetection | ctx context.Context, detectId string | (*model.Detection, error) | Get a detection by internal SOC ID |
| GetDetectionByPublicId | ctx context.Context, publicId string | (*model.Detection, error) | Get a detection by its public (SID/rule) ID |
| UpdateDetection | ctx context.Context, detect *model.Detection | (*model.Detection, error) | Update an existing detection |
| BulkUpdateDetections | ctx context.Context, newStatus bool, detects []*model.Detection, logger log.Interface | (*model.BulkUpdateStats, error) | Bulk enable/disable detections |
| BulkAddOverrides | ctx context.Context, newOverrides []*model.Override, detects []*model.Detection, logger log.Interface | (*model.BulkUpdateStats, error) | Bulk-add overrides to detections |
| DeleteDetection | ctx context.Context, detectID string | (*model.Detection, error) | Delete a detection by ID |
| GetAllDetections | ctx context.Context, opts ...model.GetAllOption | (map[string]*model.Detection, error) | Get all detections as map keyed by PublicId; supports filter options (engine, community) |
| Query | ctx context.Context, query string, max int | ([]interface{}, error) | Execute a raw query against the detection index |
| QueryWithRange | ctx context.Context, query string, rangeStart string, rangeEnd string, rangeFormat string, limit int | (*model.EventSearchResults, error) | Query detections within a time range |
| ConvertEventsToDetections | ctx context.Context, detectEvents *model.EventSearchResults | (detects []*model.Detection, err error) | Convert raw event search results into Detection objects |
| GetDetectionHistory | ctx context.Context, detectID string | ([]interface{}, error) | Get the audit history of a detection |
| CreateComment | ctx context.Context, newComment *model.DetectionComment | (*model.DetectionComment, error) | Add a comment to a detection |
| GetComment | ctx context.Context, commentId string | (*model.DetectionComment, error) | Get a detection comment by ID |
| GetComments | ctx context.Context, detectionId string | ([]*model.DetectionComment, error) | Get all comments for a detection |
| UpdateComment | ctx context.Context, comment *model.DetectionComment | (*model.DetectionComment, error) | Update a detection comment |
| DeleteComment | ctx context.Context, id string | error | Delete a detection comment by ID |
| DoesTemplateExist | ctx context.Context, tmpl string | (bool, error) | Check if an ES index template exists |
| BuildBulkIndexer | ctx context.Context, logger log.Interface | (esutil.BulkIndexer, error) | Build an ES bulk indexer for batch detection operations |
| ConvertObjectToDocument | ctx context.Context, kind string, obj any, auditable *model.Auditable, isEdit bool, auditDocId *string, op *string | (doc []byte, index string, err error) | Serialize a detection object to an ES document with audit metadata |

---

## Assistantstore
**File:** `server/assistantstore.go`
**Implemented by:** `elastic` (server/modules/elastic)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| SaveChat | ctx context.Context, msg *model.StoredMessage | error | Persist a chat message |
| GetChatHistory | ctx context.Context, sessionId string | ([]*model.StoredMessage, error) | Get chat history for a session |
| GetSessions | ctx context.Context, opts ...model.GetSessionsOpt | ([]*model.AssistantSession, error) | List assistant sessions with optional filters |
| CreateSession | ctx context.Context, session *model.AssistantSession | error | Create a new assistant session |
| UpdateSessionTags | ctx context.Context, sessionId string, tags []string | error | Update tags on a session |
| DeleteSession | ctx context.Context, sessionId string | error | Delete an assistant session |
| GetUsage | ctx context.Context, start time.Time, end time.Time | ([]*model.UserUsage, error) | Get AI usage statistics for a time range |

---

## Playbookstore
**File:** `server/playbookstore.go`
**Implemented by:** `playbook` (server/modules/playbook)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| Interrupt | ctx context.Context, force bool | error | Interrupt any running playbook execution |
| GetPlaybooksForDetection | ctx context.Context, detectId string, detectCategory string, detectEngine model.EngineName | ([]*model.Playbook, error) | Get playbooks applicable to a detection by ID, category, and engine |
| GetPlaybookById | ctx context.Context, id string | (*model.Playbook, error) | Get a playbook by ID |
| ConvertQuestions | ctx context.Context, queries []string | ([]*model.ConvertedQuery, error) | Convert natural-language questions to search queries |
| ExecutePlaybookSearches | ctx context.Context, event *model.EventRecord, pbs []*model.Playbook | error | Execute all searches defined in playbooks against an event |
| GetEventSpecificPlaybook | ctx context.Context, id string | ([]*model.Playbook, error) | Get playbooks specific to an event ID |

---

## Configstore
**File:** `server/configstore.go`
**Implemented by:** `salt` (server/modules/salt)

> Also has an in-memory implementation: `MemConfigStore` in `server/memconfigstore.go`.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| GetSettings | ctx context.Context, advanced bool | ([]*model.Setting, error) | Get all settings; if advanced=true, include advanced/hidden settings |
| UpdateSetting | ctx context.Context, setting *model.Setting, remove bool | error | Update or remove a setting |
| SyncSettings | ctx context.Context | error | Synchronize settings from the upstream config management system |
| SyncModule | ctx context.Context, module string, force bool | error | Synchronize a specific module's config; force=true to overwrite |

---

## GridMembersstore
**File:** `server/gridmembersstore.go`
**Implemented by:** `salt` (server/modules/salt)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| GetMembers | ctx context.Context | ([]*model.GridMember, error) | Get all grid members (minions) |
| ManageMember | ctx context.Context, operation string, id string | error | Manage a grid member (e.g. accept, reject, delete) |
| SendFile | ctx context.Context, node string, from string, to string, cleanup bool | error | Send a file to a grid node; optionally clean up source |
| Import | ctx context.Context, node string, file string, importer string | (*string, error) | Import a file on a node using a specified importer; returns job ID |

---

## Rolestore
**File:** `server/rolestore.go`
**Implemented by:** `staticrbac` (server/modules/staticrbac)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| Reload | (none) | (none) | Reload role definitions from disk/config |
| GetAssignments | ctx context.Context | (map[string][]string, error) | Get all role assignments (userId -> roles) |
| GetRolesForAuthId | ctx context.Context, id string | (error, []string) | Get the roles assigned to an auth ID |
| GetRoles | ctx context.Context | []string | Get top-level roles (roles that are not children of another role) |
| GetPermissions | ctx context.Context | map[string][]string | Get role->permissions mapping |
| EnsureDefaultRoleForUser | ctx context.Context | error | Ensure the current user has at least the default role |

---

## Statusstore
**File:** `server/statusstore.go`
**Implemented by:** `sostatus` (server/modules/sostatus)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| GetStatusSummary | ctx context.Context | (*model.Status, error) | Get the overall grid status summary |

---

## Metrics
**File:** `server/metrics.go`
**Implemented by:** `influxdb` (server/modules/influxdb)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| GetGridEps | ctx context.Context | int | Get the grid-wide events-per-second metric |
| UpdateNodeMetrics | ctx context.Context, node *model.Node | bool | Update metrics on a node; returns true if changed |

---

## DetectionEngine
**File:** `server/detectionengine.go`
**Implemented by:** `suricataengine` (server/modules/suricata), `elastalertengine` (server/modules/elastalert), `strelkaengine` (server/modules/strelka)

> Registered at runtime via `srv.DetectionEngines.Store(model.EngineName, engine)`.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| ValidateRule | rule string | (string, error) | Validate a detection rule; returns normalized rule or error |
| SyncLocalDetections | ctx context.Context, detections []*model.Detection | (errMap map[string]string, err error) | Sync detections to the local engine; returns per-detection errors |
| ConvertRule | ctx context.Context, detect *model.Detection | (string, error) | Convert a detection into the engine's native rule format |
| ExtractDetails | detect *model.Detection | error | Extract metadata (title, severity, etc.) from a detection's rule content |
| InterruptSync | forceFull bool, notify bool | (none) | Interrupt the current sync; optionally force a full re-sync and notify |
| DuplicateDetection | ctx context.Context, detection *model.Detection | (*model.Detection, error) | Duplicate a detection with a new public ID |
| GetState | (none) | *model.EngineState | Get the engine's current sync/status state |
| GenerateUnusedPublicId | ctx context.Context | (string, error) | Generate a public ID not yet in use |
| ApplyFilters | detect *model.Detection | (didFilterAct bool, err error) | Apply engine-specific filters; returns whether the filter modified the detection |
| MergeAuxiliaryData | detect *model.Detection | error | Merge auxiliary/supplemental data into the detection |

---

## AssistantManager
**File:** `server/assistantmanager.go`
**Implemented by:** `assistant` (server/modules/assistant)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| Chat | ctx context.Context, aiModel string, messages []*model.Message, opts ...model.ChatOpt | ([]*model.Message, error) | Send messages and get AI response (non-streaming) |
| ChatStream | ctx context.Context, aiModel string, messages []*model.Message | (*http.Response, *model.AuxMessageData, error) | Send messages and get a streaming AI response |
| ExecuteTool | ctx context.Context, toolName string, params string, auxData string | (*model.ToolResponse, error) | Execute a tool call requested by the AI |
| Balance | ctx context.Context, aiModel string | (*model.BalanceResponse, error) | Get the remaining balance/quota for a model |
| Health | ctx context.Context, aiModel string | (*model.HealthResponse, error) | Check health/availability of a model endpoint |

---

## AssistantAdapter
**File:** `server/assistantmanager.go`
**Implemented by:** `GeminiAdapter` (server/modules/assistant/gemini_adapter.go), `OpenAIChatAdapter` (server/modules/assistant/openai_chat_adapter.go), `OpenAIResponsesAdapter` (server/modules/assistant/openai_responses_adapter.go), `SOAiCloudAdapter` (server/modules/assistant/soai_adapter.go)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| Protocol | (none) | string | Return the adapter's protocol identifier (e.g. "openai", "gemini") |
| SendMessage | ctx context.Context, req *model.ChatRequest | (*model.Message, error) | Send a chat request and receive a response message |
| SendMessageStream | ctx context.Context, req *model.ChatRequest | (*http.Response, *model.AuxMessageData, error) | Send a chat request and receive a streaming response |
| GetBalance | ctx context.Context | (*model.BalanceResponse, error) | Get remaining balance/quota |
| GetHealth | ctx context.Context | (*model.HealthResponse, error) | Check adapter health |

---

## IOManager
**File:** `server/modules/detections/io_manager.go`
**Implemented by:** `ResourceManager` (server/modules/detections/io_manager.go)

> Abstraction over filesystem, HTTP, and git operations used by detection engines.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| ReadFile | path string | ([]byte, error) | Read a file's contents |
| WriteFile | path string, contents []byte, perm fs.FileMode | error | Write contents to a file with given permissions |
| DeleteFile | path string | error | Delete a single file |
| ReadDir | path string | ([]os.DirEntry, error) | List entries in a directory |
| RemoveAll | path string | error | Recursively remove a directory |
| Stat | path string | (os.FileInfo, error) | Get file/directory info |
| MakeRequest | req *http.Request, streaming bool | (*http.Response, error) | Execute an HTTP request; streaming=true disables compression |
| ExecCommand | cmd *exec.Cmd | (output []byte, exitCode int, runtime time.Duration, err error) | Execute an OS command; returns output, exit code, and duration |
| WalkDir | root string, fn fs.WalkDirFunc | error | Recursively walk a directory tree |
| CloneRepo | ctx context.Context, path string, repo string, branch *string | error | Clone a git repo (shallow, single-branch) |
| PullRepo | ctx context.Context, path string, branch *string | (pulled bool, reclone bool, failSync bool) | Pull a git repo; returns status flags for caller to decide next action |

---

## Authorizer
**File:** `rbac/authorizer.go`
**Implemented by:** `staticrbac` (server/modules/staticrbac)

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| CheckContextOperationAuthorized | ctx context.Context, operation string, target string | error | Check if the user in context is authorized for an operation on a target |
| CheckUserOperationAuthorized | userId string, operation string, target string | error | Check if a specific user is authorized for an operation on a target |

---

## Module
**File:** `module/module.go`
**Implemented by:** All modules listed in `server/modules/modules.go`

> Base interface for all pluggable server modules.

| Method | Params | Returns | Description |
|--------|--------|---------|-------------|
| PrerequisiteModules | (none) | []string | Return module names that must be initialized before this one |
| Init | config ModuleConfig | error | Initialize the module with its configuration |
| Start | (none) | error | Start the module (begin background work) |
| Stop | (none) | error | Stop the module (clean shutdown) |
| IsRunning | (none) | bool | Return whether the module is currently running |

---

## Module-to-Interface Implementation Map

> Derived from `server/modules/modules.go` and interface assignment sites across the codebase.

| Module Key | Go Package | Interfaces Implemented |
|------------|------------|----------------------|
| `filedatastore` | server/modules/filedatastore | Datastore |
| `elastic` | server/modules/elastic | Eventstore, Casestore, Detectionstore, Assistantstore |
| `elasticcases` | server/modules/elasticcases | Casestore |
| `httpcase` | server/modules/generichttp | Casestore |
| `thehive` | server/modules/thehive | Casestore |
| `kratos` | server/modules/kratos | Userstore |
| `hydra` | server/modules/hydra | Clientstore |
| `salt` | server/modules/salt | Configstore, GridMembersstore, AdminUserstore, AdminClientstore |
| `staticrbac` | server/modules/staticrbac | Rolestore, Authorizer |
| `sostatus` | server/modules/sostatus | Statusstore |
| `influxdb` | server/modules/influxdb | Metrics |
| `suricataengine` | server/modules/suricata | DetectionEngine (registered as `model.EngineNameSuricata`) |
| `elastalertengine` | server/modules/elastalert | DetectionEngine (registered as `model.EngineNameElastAlert`) |
| `strelkaengine` | server/modules/strelka | DetectionEngine (registered as `model.EngineNameStrelka`) |
| `playbook` | server/modules/playbook | Playbookstore |
| `assistant` | server/modules/assistant | AssistantManager |
| `navigator` | server/modules/navigator | _(no store interface; reads from Eventstore and Detectionstore)_ |
| `statickeyauth` | server/modules/statickeyauth | _(HTTP preprocessor/auth; no store interface)_ |

### AssistantAdapter Implementations

| Adapter Struct | File | Protocol |
|---------------|------|----------|
| GeminiAdapter | server/modules/assistant/gemini_adapter.go | gemini |
| OpenAIChatAdapter | server/modules/assistant/openai_chat_adapter.go | openai (chat completions) |
| OpenAIResponsesAdapter | server/modules/assistant/openai_responses_adapter.go | openai (responses) |
| SOAiCloudAdapter | server/modules/assistant/soai_adapter.go | soai |

### IOManager Implementation

| Struct | File | Notes |
|--------|------|-------|
| ResourceManager | server/modules/detections/io_manager.go | Wraps OS filesystem, HTTP client, and go-git for detection engine sync operations |

---

## Supporting Types

These types are referenced by interfaces but defined elsewhere:

| Type | Package | Notes |
|------|---------|-------|
| ModuleConfig | module | `map[string]interface{}` |
| ModuleConfigMap | module | `map[string]ModuleConfig` |
| SyncStatus | server | Struct with Engine (model.EngineName) and Status (string) fields |
| MemConfigStore | server | In-memory Configstore implementation for testing |
