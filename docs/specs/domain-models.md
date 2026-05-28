# Domain Models Specification

> Extracted from Go source code in model/*.go. This is the contract for the Python rewrite.

Perfect! Now I have read all the model files. Let me compile this into a comprehensive specification document for the Python rewrite.

## EXHAUSTIVE DOMAIN MODEL SPECIFICATION

I have completed a thorough extraction of all domain models from the Security Onion SOC Go codebase. Here is the complete specification for your Python rewrite:

---

### STRUCT SPECIFICATIONS

#### 1. ANALYZER
**File:** `analyzer.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | None |
| Path | string | path | Yes | None |

**Methods:**
- `GetModule()`: Returns `Id + "." + Id`
- `GetRequirementsPath()`: Returns `Path + "/requirements.txt"`
- `GetSitePackagesPath()`: Returns `Path + "/site-packages"`
- `GetSourcePackagesPath()`: Returns `Path + "/source-packages"`

---

#### 2. AUDITABLE (Base Struct)
**File:** `case.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id, omitempty | No | None |
| CreateTime | *time.Time | createTime | No | None |
| UpdateTime | *time.Time | updateTime, omitempty | No | None |
| UserId | string | userId | No | None |
| Kind | string | kind, omitempty | No | None |
| Operation | string | operation, omitempty | No | None |

**Notes:** All fields are read-only and server-generated.

---

#### 3. CASE
**File:** `case.go`
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| StartTime | *time.Time | startTime | No | optional |
| CompleteTime | *time.Time | completeTime | No | optional |
| Title | string | title | No | optional |
| Description | string | description | No | optional |
| Priority | int | priority | No | optional |
| Severity | string | severity | No | optional |
| Status | string | status | No | optional |
| Template | string | template | No | optional |
| Tlp | string | tlp | No | optional |
| Pap | string | pap | No | optional |
| Category | string | category | No | optional |
| AssigneeId | string | assigneeId | No | optional |
| Tags | []string | tags | No | optional |

**Constants:**
- `CASE_STATUS_NEW = "new"`

**Methods:**
- `ProcessWorkflowForStatus(oldCase *Case)`: Updates StartTime/CompleteTime based on status transitions

---

#### 4. COMMENT
**File:** `case.go`
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| CaseId | string | caseId | Yes | required |
| Description | string | description | Yes | required |
| Hours | float64 | hours | No | optional |

---

#### 5. RELATED_EVENT
**File:** `case.go`
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| CaseId | string | caseId | Yes | required |
| Fields | map[string]interface{} | fields | Yes | required |

---

#### 6. ATTACH_EVENT_CRITERIA
**File:** `case.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| CaseId | string | caseId | Yes | required |
| Fields | map[string]interface{} | fields | Yes | required |
| DateRange | string | dateRange, omitempty | No | None |
| DateRangeFormat | string | dateRangeFormat, omitempty | No | None |
| Timezone | string | timezone, omitempty | No | None |
| Escalated | bool | escalated | Yes | None |
| Acknowledged | bool | acknowledged | Yes | None |

---

#### 7. ARTIFACT
**File:** `case.go`
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| CaseId | string | caseId | Yes | required |
| GroupType | string | groupType | No | None |
| GroupId | string | groupId | No | None |
| ArtifactType | string | artifactType | Yes | required |
| Value | string | value | Yes | required |
| MimeType | string | mimeType | No | None |
| StreamLen | int | streamLength | No | None |
| StreamId | string | streamId | No | None |
| Tlp | string | tlp | No | optional |
| Tags | []string | tags | No | optional |
| Description | string | description | No | optional |
| Ioc | bool | ioc | No | optional |
| Md5 | string | md5 | No | optional |
| Sha1 | string | sha1 | No | optional |
| Sha256 | string | sha256 | No | optional |
| Protected | bool | protected | No | optional |

**Methods:**
- `Write(reader io.Reader)`: Computes MIME type and hash values (MD5, SHA-1, SHA-256) from input bytes

---

#### 8. ARTIFACT_STREAM
**File:** `case.go`
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Content | string | content | Yes | required (base64-encoded) |

**Methods:**
- `Write(reader io.Reader)`: Base64-encodes input, computes hashes
- `Read()`: Returns base64-decoded reader

---

#### 9. CLIENT
**File:** `client.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | Max 55 chars, must start with "socl_" |
| CreateTime | time.Time | createTime | Yes | None |
| UpdateTime | time.Time | updateTime | No | None |
| Name | string | name | Yes | Max 50 chars |
| Secret | string | secret | Yes | Returned only on creation/regeneration |
| Permissions | []string | permissions | No | Each max 50 chars |
| Note | string | note | No | Max 100 chars |
| SearchUsername | string | searchUsername | No | Max 50 chars |

**Constants:**
- `API_CLIENT_PREFIX = "socl_"`
- `MAX_CLIENT_ID_LEN = 55`
- `MAX_CLIENT_NAME_LEN = 50`
- `MAX_PERMISSION_LEN = 50`

**Validation Methods:**
- `Verify()`: Checks all field length constraints

---

#### 10. CLIENT_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| HuntingParams | HuntingParameters | hunt | Yes | Must verify |
| AlertingParams | AlertingParameters | alerts | Yes | Must verify |
| CasesParams | HuntingParameters | cases | Yes | Must verify |
| CaseParams | CaseParameters | case | Yes | Must verify |
| DashboardsParams | HuntingParameters | dashboards | Yes | Must verify |
| JobParams | HuntingParameters | job | Yes | Must verify |
| DetectionsParams | DetectionsParameters | detections | Yes | Must verify |
| DetectionParams | DetectionParameters | detection | Yes | Must verify |
| DocsUrl | string | docsUrl | No | None |
| CheatsheetUrl | string | cheatsheetUrl | No | None |
| ReleaseNotesUrl | string | releaseNotesUrl | No | None |
| GridParams | GridParameters | grid | No | None |
| WebSocketTimeoutMs | int | webSocketTimeoutMs | No | None |
| TipTimeoutMs | int | tipTimeoutMs | No | None |
| ApiTimeoutMs | int | apiTimeoutMs | No | None |
| CacheExpirationMs | int | cacheExpirationMs | No | None |
| InactiveTools | []string | inactiveTools | No | None |
| Tools | []ClientTool | tools | No | None |
| CasesEnabled | bool | casesEnabled | No | None |
| DetectionsEnabled | bool | detectionsEnabled | No | None |
| ExportNodeId | string | exportNodeId | No | None |
| AssistantParams | AssistantParameters | assistant | No | None |

---

#### 11. CLIENT_TOOL
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name | Yes | None |
| Description | string | description | Yes | None |
| Target | string | target | Yes | None |
| Icon | string | icon | Yes | None |
| Link | string | link | Yes | None |

---

#### 12. HUNTING_QUERY
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name | Yes | None |
| Description | string | description | Yes | None |
| Query | string | query | Yes | None |
| ShowSubtitle | bool | showSubtitle | Yes | None |

---

#### 13. HUNTING_ACTION
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name | Yes | None |
| Description | string | description | Yes | None |
| Icon | string | icon | Yes | None |
| Link | string | link | Yes | None |
| Links | []string | links | No | None |
| Fields | []string | fields | No | None |
| Target | string | target | Yes | None |
| Background | bool | background | Yes | None |
| BackgroundSuccessLink | string | backgroundSuccessLink | No | None |
| BackgroundFailureLink | string | backgroundFailureLink | No | None |
| Method | string | method | Yes | None |
| Body | string | body | Yes | None |
| Options | map[string]interface{} | options | No | None |
| Categories | []string | categories | No | None |
| JSCall | string | jsCall | No | None |

---

#### 14. TOGGLE_FILTER
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name | Yes | None |
| Filter | string | filter | Yes | None |
| Enabled | bool | enabled | Yes | None |
| Exclusive | bool | exclusive | Yes | None |
| EnablesToggles | []string | enablesToggles | No | None |
| DisablesToggles | []string | disablesToggles | No | None |

---

#### 15. HUNTING_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| GroupItemsPerPage | int | groupItemsPerPage | Yes | None |
| GroupFetchLimit | int | groupFetchLimit | Yes | Defaults to DEFAULT_GROUP_FETCH_LIMIT (10) if ≤ 0 |
| EventItemsPerPage | int | eventItemsPerPage | Yes | None |
| EventFetchLimit | int | eventFetchLimit | Yes | Defaults to DEFAULT_EVENT_FETCH_LIMIT (100) if ≤ 0 |
| RelativeTimeValue | int | relativeTimeValue | Yes | Defaults to DEFAULT_RELATIVE_TIME_VALUE (24) if ≤ 0 |
| RelativeTimeUnit | int | relativeTimeUnit | Yes | Defaults to DEFAULT_RELATIVE_TIME_UNIT (30) if ≤ 0 |
| MostRecentlyUsedLimit | int | mostRecentlyUsedLimit | Yes | Defaults to 0 if < 0 |
| EventFields | map[string][]string | eventFields | No | None |
| SafeStringMaxLength | int | safeStringMaxLength | Yes | Defaults to DEFAULT_SAFE_STRING_MAX_LENGTH (100) if ≤ 0 |
| QueryBaseFilter | string | queryBaseFilter | No | None |
| QueryToggleFilters | []*ToggleFilter | queryToggleFilters | No | None |
| Queries | []*HuntingQuery | queries | No | None |
| Actions | []*HuntingAction | actions | No | None |
| Advanced | bool | advanced | Yes | None |
| AckEnabled | bool | ackEnabled | Yes | None |
| EscalateEnabled | bool | escalateEnabled | Yes | None |
| EscalateRelatedEventsEnabled | bool | escalateRelatedEventsEnabled | Yes | None |
| ViewEnabled | bool | viewEnabled | Yes | None |
| CreateLink | string | createLink | No | None |
| ChartLabelMaxLength | int | chartLabelMaxLength | Yes | Defaults to DEFAULT_CHART_LABEL_MAX_LENGTH (35) if ≤ 0 |
| ChartLabelOtherLimit | int | chartLabelOtherLimit | Yes | Defaults to DEFAULT_CHART_LABEL_OTHER_LIMIT (10) if ≤ 0 |
| ChartLabelFieldSeparator | string | chartLabelFieldSeparator | Yes | Defaults to DEFAULT_CHART_LABEL_FIELD_SEPARATOR (", ") if empty |
| AggregationActionsEnabled | bool | aggregationActionsEnabled | Yes | None |
| DetectionEngineStatusQueries | string | detectionEngineStatusQueries | No | None |

**Methods:**
- `Verify()`: Validates and applies defaults to all numeric fields, combines deprecated Link into Links array

---

#### 16. ALERTING_PARAMETERS
**File:** `clientparameters.go`
**Inherits:** HuntingParameters

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| MaxBulkEscalateEvents | int | maxBulkEscalateEvents | Yes | None |

---

#### 17. ASSISTANT_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Enabled | bool | enabled | Yes | None |
| InvestigationPrompt | string | investigationPrompt | No | None |
| CompressContextPrompt | string | compressContextPrompt | No | None |
| ThresholdColorRatioLow | float64 | thresholdColorRatioLow | No | None |
| ThresholdColorRatioMed | float64 | thresholdColorRatioMed | No | None |
| ThresholdColorRatioMax | float64 | thresholdColorRatioMax | No | None |
| AvailableModels | []ModelParameters | availableModels | No | None |
| AvailableAdapters | []AdapterParameters | availableAdapters | No | None |

---

#### 18. MODEL_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| ID | string | id | Yes | None |
| DisplayName | string | displayName | Yes | None |
| ContextLimitSmall | int | contextLimitSmall | No | Parsed from numeric or scientific notation |
| ContextLimitLarge | int | contextLimitLarge | No | Parsed from numeric or scientific notation |
| CharsPerTokenEstimate | float64 | charsPerTokenEstimate | No | None |
| LowBalanceColorAlert | int | lowBalanceColorAlert | No | Parsed from numeric or scientific notation |
| Origin | string | origin | No | None |
| Adapter | string | adapter | No | None |
| Enabled | bool | enabled | No | None |

**Custom UnmarshalJSON:** Handles numeric or scientific-notation string fields for context limits and alert thresholds.

---

#### 19. ADAPTER_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name | Yes | None |
| Protocol | string | protocol | Yes | None |

---

#### 20. PRESET_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Labels | []string | labels | No | None |
| CustomEnabled | bool | customEnabled | Yes | None |

---

#### 21. CASE_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| MostRecentlyUsedLimit | int | mostRecentlyUsedLimit | Yes | Defaults to 0 if < 0 |
| RenderAbbreviatedCount | int | renderAbbreviatedCount | Yes | None |
| AnalyzerNodeId | string | analyzerNodeId | No | None |
| Presets | map[string]PresetParameters | presets | No | None |

---

#### 22. GRID_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| MaxUploadSize | uint64 | maxUploadSize, omitempty | No | None |
| StaleMetricsMs | uint64 | staleMetricsMs, omitempty | No | None |

---

#### 23. DETECTIONS_PARAMETERS
**File:** `clientparameters.go`
**Inherits:** HuntingParameters

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Presets | map[string]PresetParameters | presets | No | None |

---

#### 24. DETECTION_PARAMETERS
**File:** `clientparameters.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Presets | map[string]PresetParameters | presets | No | None |
| SeverityTranslations | map[string]string | severityTranslations | No | None |
| TemplateDetections | map[string]string | templateDetections | No | None |
| ShowUnreviewedAiSummaries | bool | showUnreviewedAiSummaries | Yes | None |

---

#### 25. COMPILATION_REPORT
**File:** `compilation_report.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Timestamp | string | timestamp | Yes | None |
| Success | []string | success | No | None |
| Failure | []string | failure | No | None |
| CompiledRulesHash | string | compiled_sha256 | No | None |

---

#### 26. UI_ELEMENT
**File:** `config.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Field | string | field | Yes | None |
| Label | string | label | Yes | None |
| Multiline | bool | multiline | Yes | None |
| ForcedType | string | forcedType | No | None |
| Options | []string | options | No | None |
| OptionSeparator | string | optionSeparator | No | None |
| Default | interface{} | default | No | None |
| Required | bool | required | Yes | None |
| Readonly | bool | readonly | Yes | None |
| Regex | string | regex | No | None |
| RegexFailureMessage | string | regexFailureMessage | No | None |

---

#### 27. SETTING
**File:** `config.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | Must match regex `^[a-zA-Z0-9\*\/:_.-]+$` |
| Title | string | title | No | None |
| Description | string | description | No | None |
| Global | bool | global | Yes | None |
| Node | bool | node | Yes | None |
| NodeId | string | nodeId | No | None |
| Default | string | default | No | None |
| DefaultAvailable | bool | defaultAvailable | Yes | None |
| Value | string | value | No | None |
| Multiline | bool | multiline | Yes | None |
| Readonly | bool | readonly | Yes | None |
| ReadonlyUi | bool | readonlyUi | Yes | None |
| Sensitive | bool | sensitive | Yes | None |
| Regex | string | regex | No | None |
| RegexFailureMessage | string | regexFailureMessage | No | None |
| Required | bool | required | Yes | None |
| File | bool | file | Yes | None |
| Advanced | bool | advanced | Yes | None |
| HelpLink | string | helpLink | No | None |
| Syntax | string | syntax | No | None |
| ForcedType | string | forcedType | No | None |
| Duplicates | bool | duplicates | Yes | None |
| JinjaEscaped | bool | jinjaEscaped | Yes | None |
| Options | []string | options | No | None |
| OptionSeparator | string | optionSeparator | No | None |
| UiElements | []UiElement | uiElements | No | None |
| UiElementsDeleteMessage | string | uiElementsDeleteMessage | No | None |

**Methods:**
- `SupportsJinja()`: Returns true if Syntax != "json" && (JinjaEscaped || IsDuplicatedSetting())
- `IsDuplicatedSetting()`: Returns true if Description is empty

**Validation:**
- `IsValidMinionId(id string)`: Regex `^[a-zA-Z0-9_.-]+$`
- `IsValidSettingId(id string)`: Regex `^[a-zA-Z0-9\*\/:_.-]+$`

---

#### 28. CUSTOM_RULESET
**File:** `custom_ruleset.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Community | bool | community | Yes | None |
| License | string | license | Yes | required |
| Url | string | url | No | None |
| TargetFile | string | target-file | No | None |
| File | string | file | No | None |
| Ruleset | string | ruleset | Yes | required |

**Validation:**
- Either `File` OR (`Url` + `TargetFile`) must be provided
- If `Url` provided, `TargetFile` required
- If `TargetFile` provided, `Url` required
- File extension should be `.rules`

---

#### 29. DETECTION_ENGINE (Type Alias + Struct)
**File:** `detection.go`

**Type Aliases:**
- `ScanType` (string): files, packets, files,packets, elastic
- `SigLanguage` (string): sigma, suricata, yara
- `Severity` (string): unknown, informational, low, medium, high, critical
- `IDType` (string): uuid, sid
- `EngineName` (string): suricata, strelka, elastalert
- `OverrideType` (string): suppress, threshold, modify, customFilter

**Constants:**
- ScanType: `ScanTypeFiles`, `ScanTypePackets`, `ScanTypePacketsAndFiles`, `ScanTypeElastic`
- SigLanguage: `SigLangSigma`, `SigLangSuricata`, `SigLangYara`
- Severity: `SeverityUnknown`, `SeverityInformational`, `SeverityLow`, `SeverityMedium`, `SeverityHigh`, `SeverityCritical`
- IDType: `IDTypeUUID`, `IDTypeSID`
- EngineName: `EngineNameSuricata`, `EngineNameStrelka`, `EngineNameElastAlert`
- OverrideType: `OverrideTypeSuppress`, `OverrideTypeThreshold`, `OverrideTypeModify`, `OverrideTypeCustomFilter`
- Track: `TrackBySrc`, `TrackByDst`, `TrackByEither`, `TrackByBoth`
- ThresholdType: `ThresholdTypeLimit`, `ThresholdTypeThreshold`, `ThresholdTypeBoth`
- License: `LicenseDRL`, `LicenseCommercial`, `LicenseBSD`, `LicenseUnknown`

**Struct Definition:**

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name | Yes | enum: elastalert, strelka, suricata |
| IDType | IDType | idType | Yes | enum: sid, uuid |
| ScanType | ScanType | scanType | Yes | enum: files, packets, elastic |
| SigLanguage | SigLanguage | sigLanguage | Yes | enum: sigma, suricata, yara |

---

#### 30. DETECTION
**File:** `detection.go`
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| PublicID | string | publicId | No | None |
| Title | string | title | Yes | None |
| Severity | Severity | severity | Yes | enum: unknown, informational, low, medium, high, critical |
| Author | string | author | No | None |
| Category | string | category, omitempty | No | None |
| Description | string | description | No | None |
| Content | string | content | No | None |
| IsEnabled | bool | isEnabled | Yes | None |
| IsReporting | bool | isReporting | Yes | None |
| IsCommunity | bool | isCommunity | Yes | None |
| Engine | EngineName | engine | Yes | Must be valid engine name |
| Language | SigLanguage | language | Yes | enum: sigma, suricata, yara |
| Overrides | []*Override | overrides | No | None |
| Tags | []string | tags | No | None |
| Ruleset | string | ruleset | No | None |
| License | string | license | No | None |
| SourceCreated | *time.Time | sourceCreated | No | None |
| SourceUpdated | *time.Time | sourceUpdated | No | None |
| Product | string | product, omitempty | No | None |
| Service | string | service, omitempty | No | None |
| AiFields | *AiFields | (embedded) | No | None |
| PendingDelete | bool | - (transient) | No | Internal use only |
| PersistChange | bool | - (transient) | No | Internal use only |

**Validation:**
- `Validate()`: Engine must be supported, all overrides must validate

---

#### 31. AI_FIELDS
**File:** `detection.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| AiSummary | string | aiSummary | No | None |
| AiSummaryReviewed | bool | aiSummaryReviewed | No | None |
| IsAiSummaryStale | bool | isSummaryStale | No | None |

---

#### 32. DETECTION_COMMENT
**File:** `detection.go`
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| DetectionId | string | detectionId | Yes | None |
| Value | string | value | Yes | None |

---

#### 33. OVERRIDE
**File:** `detection.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Type | OverrideType | type | Yes | enum: customFilter, modify, suppress, threshold |
| IsEnabled | bool | isEnabled | Yes | None |
| Note | string | note | No | None |
| CreatedAt | time.Time | createdAt | Yes | None |
| UpdatedAt | time.Time | updatedAt | Yes | None |
| OverrideParameters | (embedded) | (inline) | Yes | See OverrideParameters |

**Custom YAML Marshaling:** Supports inline YAML representation.

---

#### 34. OVERRIDE_PARAMETERS
**File:** `detection.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Regex | *string | regex, omitempty | No (for modify) | Must be valid regex pattern |
| Value | *string | value, omitempty | No (for modify) | None |
| ThresholdType | *string | thresholdType, omitempty | No (for threshold) | enum: threshold, limit, both |
| Track | *string | track, omitempty | No | enum: by_src, by_dst, by_either, by_both |
| IP | *string | ip, omitempty | No (for suppress) | Must be valid CIDR or variable or bracketed list |
| Count | *int | count, omitempty | No (for threshold) | Must be > 0 |
| Seconds | *int | seconds, omitempty | No (for threshold) | Must be > 0 |
| CustomFilter | *string | customFilter, omitempty | No (for customFilter elastalert) | Must be valid YAML |

**Validation Rules:**
- **Modify (Suricata):** Requires Regex and Value; no other fields allowed
- **Suppress (Suricata):** Requires IP and Track; no Regex/Value/ThresholdType/Count/Seconds/CustomFilter
- **Threshold (Suricata):** Requires ThresholdType, Track, Count, Seconds; no Regex/Value/CustomFilter
- **CustomFilter (ElastAlert):** Requires CustomFilter; no other fields allowed
- Track values for suppress: by_src, by_dst, by_either
- Track values for threshold: by_src, by_dst, by_both
- IP validation: CIDR format (1.2.3.4/y), Suricata variables ($VAR), or bracketed lists ([ip1,ip2])
- Count and Seconds must be positive

---

#### 35. OVERRIDE_NOTE_UPDATE
**File:** `detection.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Note | string | note | Yes | None |

---

#### 36. BULK_UPDATE_STATS
**File:** `detection.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Updated | int | - | Yes | None |
| Audited | int | - | Yes | None |
| Filtered | int | - | Yes | None |
| ErrMap | map[string]string | - | No | None |
| UpdateDuration | time.Duration | - | Yes | None |
| NeedToSync | []*Detection | - | No | None |

---

#### 37. AUDIT_INFO
**File:** `detection.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| DocId | string | - | Yes | None |
| Op | string | - | Yes | None |
| Object | interface{} | - | Yes | None |

---

#### 38. AI_SUMMARY
**File:** `detection.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| PublicId | string | - | Yes | None |
| Reviewed | bool | Reviewed | Yes | None |
| Summary | string | Summary | Yes | None |
| RuleBodyHash | string | Rule-Body-Hash | Yes | None |

**YAML Tags:** Standard YAML mapping for Reviewed, Summary, Rule-Body-Hash.

---

#### 39. EVENT_RESULTS
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| CreateTime | time.Time | createTime | Yes | Initialized at creation |
| CompleteTime | time.Time | completeTime | No | Set on completion |
| ElapsedMs | int | elapsedMs | Yes | None |
| Errors | []string | errors | No | None |

---

#### 40. EVENT_SEARCH_RESULTS
**File:** `event.go`
**Inherits:** EventResults

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Criteria | *EventSearchCriteria | criteria | No | None |
| TotalEvents | int | totalEvents | Yes | None |
| Events | []*EventRecord | events | No | None |
| Metrics | map[string]([]*EventMetric) | metrics | No | None |

---

#### 41. SORT_CRITERIA
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Field | string | (example field) | Yes | None |
| Order | string | (example order) | Yes | enum: asc, desc |

---

#### 42. EVENT_SEARCH_CRITERIA
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| RawQuery | string | query | Yes | None |
| DateRange | string | dateRange | No | None |
| MetricLimit | int | metricLimit | Yes | None |
| EventLimit | int | eventLimit | Yes | Defaults to 25 |
| BeginTime | time.Time | (transient) | No | None |
| EndTime | time.Time | (transient) | No | None |
| CreateTime | time.Time | (transient) | Yes | Set at creation |
| ParsedQuery | *Query | - (transient) | No | Internal use |
| SortFields | []*SortCriteria | - (transient) | No | Internal use |
| SearchAfter | []interface{} | - (transient) | No | Internal use |

**Methods:**
- `Populate(query, dateRange, dateRangeFormat, timezone, metricLimit, eventLimit string)`: Parses input and populates criteria

---

#### 43. EVENT_METRIC
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Keys | []interface{} | keys | Yes | None |
| Value | float64 | value | Yes | None |
| Ratio | float64 | - (calculated) | No | Computed post-retrieval |
| Percentage | float64 | - (calculated) | No | Computed post-retrieval |

---

#### 44. EVENT_RECORD
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Source | string | source | Yes | Index name |
| Time | time.Time | - (transient) | No | Parsed timestamp |
| Timestamp | string | timestamp | Yes | ISO 8601 string |
| Id | string | id | Yes | Document ID |
| Type | string | type | No | Often blank |
| Score | float64 | score | No | Often 0 |
| Payload | map[string]interface{} | payload | Yes | Event data fields |
| Sort | []interface{} | sort | No | For pagination |

---

#### 45. EVENT_UPDATE_CRITERIA
**File:** `event.go`
**Inherits:** EventSearchCriteria

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| UpdateScripts | []string | updateScripts | No | Painless script syntax |
| Params | map[string]any | params | No | None |
| Asynchronous | bool | async | Yes | None |

**Methods:**
- `AddUpdateScript(script string)`: Appends script to UpdateScripts

---

#### 46. EVENT_UPDATE_RESULTS
**File:** `event.go`
**Inherits:** EventResults

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Criteria | *EventUpdateCriteria | criteria | No | None |
| UpdatedCount | int | updatedCount | Yes | None |
| UnchangedCount | int | unchangedCount | Yes | None |

**Methods:**
- `AddEventUpdateResults(newResults *EventUpdateResults)`: Aggregates counts and elapsed time

---

#### 47. EVENT_ACK_CRITERIA
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| SearchFilter | string | searchFilter | Yes | None |
| EventFilter | map[string]interface{} | eventFilter | No | None |
| DateRange | string | dateRange | No | None |
| DateRangeFormat | string | dateRangeFormat | No | None |
| Timezone | string | timezone | No | None |
| Escalate | bool | escalate | Yes | None |
| Acknowledge | bool | acknowledge | Yes | None |

---

#### 48. EVENT_INDEX_RESULTS
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Success | bool | success | Yes | None |
| DocumentId | string | id | Yes | None |

---

#### 49. EVENT_SCROLL_CRITERIA
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| RawQuery | string | query | Yes | None |
| BeginTime | time.Time | - (transient) | No | None |
| EndTime | time.Time | - (transient) | No | None |
| CreateTime | time.Time | - (transient) | Yes | None |
| ParsedQuery | *Query | - (transient) | No | Internal use |
| SortFields | []*SortCriteria | - (transient) | No | Internal use |

**Methods:**
- `Populate(query, dateRange, dateRangeFormat, timezone string)`: Parses date range with timezone support

---

#### 50. EVENT_SCROLL_RESULTS
**File:** `event.go`
**Inherits:** EventResults

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Criteria | *EventScrollCriteria | criteria | No | None |
| TotalEvents | int | totalEvents | Yes | None |
| Events | []*EventRecord | events | No | None |

---

#### 51. EVENT_MSEARCH_CRITERIA
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Index | string | - (transient) | Yes | None |
| RawQuery | string | - (transient) | Yes | None |
| ParsedQuery | *Query | - (transient) | No | Internal use |

**Methods:**
- `Populate(index, query string)`: Parses index and query

---

#### 52. EVENT_MSEARCH_RESULTS
**File:** `event.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| ElapsedMs | int | elapsedMs | Yes | None |
| Responses | []*EventSearchResults | responses | No | None |

---

#### 53. FILTER
**File:** `filter.go`

**Constants:**
- `PROTOCOL_ICMP = "icmp"`
- `PROTOCOL_TCP = "tcp"`
- `PROTOCOL_UDP = "udp"`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| ImportId | string | importId | No | None |
| BeginTime | time.Time | beginTime | No | None |
| EndTime | time.Time | endTime | No | None |
| SrcIp | string | srcIp | No | None |
| SrcPort | int | srcPort | No | None |
| DstIp | string | dstIp | No | None |
| DstPort | int | dstPort | No | None |
| Protocol | string | protocol | No | None |
| Parameters | map[string]interface{} | parameters | No | None |

---

#### 54. GRID_MEMBER
**File:** `gridmember.go`

**Constants:**
- `GridMemberAccepted = "accepted"`
- `GridMemberUnaccepted = "unaccepted"`
- `GridMemberRejected = "rejected"`
- `GridMemberDenied = "denied"`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | None |
| Name | string | name | Yes | Extracted from Id |
| Role | string | role | Yes | Extracted from Id |
| Fingerprint | string | fingerprint | Yes | SHA256 hex string |
| Status | string | status | Yes | One of the constants |

**Methods:**
- Constructor parses Id as `{name}_{role}` format

---

#### 55. INFO
**File:** `info.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Version | string | version | Yes | None |
| License | string | license | Yes | None |
| Parameters | *ClientParameters | parameters | No | None |
| ElasticVersion | string | elasticVersion | No | None |
| UserId | string | userId | No | None |
| Timezones | []string | timezones | No | None |
| SrvToken | string | srvToken | No | None |
| LicenseKey | *licensing.LicenseKey | licenseKey | No | None |
| LicenseStatus | string | licenseStatus | No | None |
| ForceUserOtp | bool | forceUserOtp | No | None |
| MgmtMac | string | mgmtMac | No | MAC address format |
| CustomReports | map[string]string | customReports | No | Filename -> title |
| Subgrids | []*Subgrid | subgrids | No | None |

---

#### 56. JOB_RESULT
**File:** `job.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | None |
| Data | interface{} | data | No | Job processor specific |
| Summary | string | summary | Yes | None |

---

#### 57. JOB
**File:** `job.go`

**Constants:**
- `JobStatusPending = 0`
- `JobStatusCompleted = 1`
- `JobStatusIncomplete = 2`
- `JobStatusDeleted = 3`
- `DEFAULT_JOB_KIND = "pcap"`
- `JOB_KIND_EXPORT = "reports"`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | int | id | Yes | None |
| CreateTime | time.Time | createTime | Yes | Set at creation |
| Status | int | status | Yes | 0-3 status codes |
| CompleteTime | time.Time | completeTime | No | None |
| FailTime | time.Time | failTime | No | None |
| Failure | string | failure | No | Error message |
| FailCount | int | failCount | Yes | None |
| Owner | string | owner | No | Unused |
| NodeId | string | nodeId | No | Case-insensitive |
| LegacySensorId | string | sensorId | No | Legacy field |
| FileExtension | string | fileExtension | Yes | Defaults to "bin" |
| Filter | *Filter | filter | No | None |
| UserId | string | userId | Yes | None |
| Kind | string | kind | No | Defaults to DEFAULT_JOB_KIND |
| Results | []*JobResult | results | No | None |
| Size | int | size | No | Stream output size |

**Methods:**
- `GetKind()`: Returns Kind or default "pcap"
- `SetNodeId(nodeId)`: Lowercase and set
- `GetNodeId()`: Lowercase accessor, fallback to LegacySensorId
- `CanProcess()`: Returns true if Status != Completed && Status != Deleted
- `Complete()`: Sets status to Completed with current time
- `Fail(err)`: Sets status to Incomplete with error
- `IsEligibleForRetry(retryIntervalMs, retryMaxAttempts)`: Checks retry conditions

---

#### 58. NODE
**File:** `node.go`

**Constants:**
- `NodeRoleDesktop = "so-desktop"`
- `NodeStatusUnknown = "unknown"`
- `NodeStatusOk = "ok"`
- `NodeStatusFault = "fault"`
- `NodeStatusPending = "pending"`
- `NodeStatusRestart = "restart"`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | None |
| OnlineTime | time.Time | onlineTime | No | None |
| UpdateTime | time.Time | updateTime | No | None |
| EpochTime | time.Time | epochTime | No | None |
| UptimeSeconds | int | uptimeSeconds | Yes | None |
| Description | string | description | No | None |
| MgmtMac | string | mgmtMac | Yes | MAC address |
| Address | string | address | Yes | IP address |
| Role | string | role | Yes | so-standalone, so-manager, etc |
| Model | string | model | No | Appliance model or N/A |
| ImageFront | string | imageFront | No | Front image filename |
| ImageBack | string | imageBack | No | Back image filename |
| Status | string | status | Yes | unknown, ok, fault, pending, restart |
| Version | string | version | Yes | Version string |
| ConnectionStatus | string | connectionStatus | Yes | unknown, ok, fault |
| RaidStatus | string | raidStatus | Yes | unknown, ok, fault |
| ProcessStatus | string | processStatus | Yes | unknown, ok, fault |
| ProcessJson | string | processJson | Yes | JSON status data |
| ProductionEps | int | productionEps | Yes | Defaults to 0 |
| ConsumptionEps | int | consumptionEps | Yes | None |
| FailedEvents | int | failedEvents | Yes | None |
| EventstoreStatus | string | eventstoreStatus | Yes | unknown, ok, fault |
| OsNeedsRestart | int | osNeedsRestart | Yes | 0 or 1 |
| OsUptimeSeconds | int | osUptimeSeconds | Yes | None |
| MetricsEnabled | bool | metricsEnabled | Yes | None |
| NonCriticalNode | bool | nonCriticalNode | Yes | None |
| DiskTotalRootGB | float64 | diskTotalRootGB | Yes | None |
| DiskUsedRootPct | float64 | diskUsedRootPct | Yes | None |
| DiskTotalNsmGB | float64 | diskTotalNsmGB | Yes | None |
| DiskUsedNsmPct | float64 | diskUsedNsmPct | Yes | None |
| CpuUsedPct | float64 | cpuUsedPct | Yes | None |
| MemoryTotalGB | float64 | memoryTotalGB | Yes | None |
| MemoryUsedPct | float64 | memoryUsedPct | Yes | None |
| SwapTotalGB | float64 | swapTotalGB | Yes | None |
| SwapUsedPct | float64 | swapUsedPct | Yes | None |
| PcapDays | float64 | pcapDays | Yes | None |
| SuriLossPct | float64 | suriLossPct | Yes | None |
| SuriRulesLoaded | int | suriRulesLoaded | Yes | None |
| SuriRulesFailed | int | suriRulesFailed | Yes | None |
| SuriRulesReloadTime | string | suriRulesReloadTime | Yes | Timestamp string |
| SuriRulesStatus | string | suriRulesStatus | Yes | ok, unknown |
| ZeekLossPct | float64 | zeekLossPct | Yes | None |
| CaptureLossPct | float64 | captureLossPct | Yes | None |
| TrafficMonInMbs | float64 | trafficMonInMbs | Yes | None |
| TrafficMonInDropsMbs | float64 | trafficMonInDropsMbs | Yes | None |
| TrafficManInMbs | float64 | trafficManInMbs | Yes | None |
| TrafficManOutMbs | float64 | trafficManOutMbs | Yes | None |
| RedisQueueSize | int | redisQueueSize | Yes | None |
| IoWaitPct | float64 | ioWaitPct | Yes | None |
| Load1m | float64 | load1m | Yes | None |
| Load5m | float64 | load5m | Yes | None |
| Load15m | float64 | load15m | Yes | None |
| DiskUsedElasticGB | float64 | diskUsedElasticGB | Yes | None |
| DiskUsedInfluxDbGB | float64 | diskUsedInfluxDbGB | Yes | None |
| HighstateAgeSeconds | int | highstateAgeSeconds | Yes | None |
| GmdEnabled | int | gmdEnabled | Yes | 0 or 1 |
| LksEnabled | int | lksEnabled | Yes | 0 or 1 |
| FpsEnabled | int | fpsEnabled | Yes | 0 or 1 |
| GridId | string | gridId | No | Subgrid ID |

**Methods:**
- `SetModel(model string)`: Sets model and image references based on appliance model
- `UpdateOverallStatus(enhancedStatusEnabled bool)`: Computes overall status from component statuses
- `IsProcessRunning(match string)`: Checks ProcessJson for running container

---

#### 59. NODE_STATUS
**File:** `node.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| StatusCode | int | status_code | Yes | None |
| Containers | []ProcessStatus | containers | Yes | None |

---

#### 60. PROCESS_STATUS
**File:** `node.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | Name | Yes | Container name |
| Status | string | Status | Yes | running, exited, etc |
| Details | string | Details | No | Details string |

---

#### 61. PACKET
**File:** `packet.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Number | int | number | Yes | Sequential number |
| Type | string | type | Yes | DNS, TCP, UDP, UNKNOWN, etc |
| SrcMac | string | srcMac | No | MAC address format |
| DstMac | string | dstMac | No | MAC address format |
| SrcIp | string | srcIp | No | IP address |
| SrcPort | int | srcPort | No | Port number |
| DstIp | string | dstIp | No | IP address |
| DstPort | int | dstPort | No | Port number |
| Length | int | length | Yes | Packet size in bytes |
| Timestamp | time.Time | timestamp | Yes | Capture time |
| Sequence | int | sequence | No | TCP sequence number |
| Acknowledge | int | acknowledge | No | TCP ACK number |
| Window | int | window | No | TCP window size |
| Checksum | int | checksum | No | Checksum value |
| Flags | []string | flags | No | SYN, ACK, FIN, PSH, etc |
| Payload | string | payload | No | Base64-encoded bytes |
| PayloadOffset | int | payloadOffset | No | Application payload offset |

---

#### 62. PLAYBOOK
**File:** `playbook.go`
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name | Yes | None |
| Description | string | description | Yes | None |
| SourceCreated | time.Time | created | Yes | None |
| SourceUpdated | *time.Time | modified, omitempty | No | None |
| DetectionId | string | detection_id | No | Specific detection UUID |
| DetectionCategory | string | detection_category | No | e.g., process_creation |
| DetectionType | string | detection_type | No | enum: nids, sigma, yara |
| Contributors | []string | contributors | No | Author names |
| Questions | []*Question | questions | No | None |

**YAML Tags:** Supports YAML inline format.

---

#### 63. QUESTION
**File:** `playbook.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Question | string | question | Yes | Human-readable question |
| Context | string | context | No | Context/rationale |
| Range | *string | range, omitempty | No | Time range hint (e.g., "+/-3d") |
| AnswerSources | []string | answer_sources | No | Where answers can be found |
| Query | string | query | Yes | Sigma YAML query |
| FilledQuery | string | filledQuery, omitempty | No | After variable substitution |
| QueryResults | []*EventRecord | queryResults | No | Query results |
| QueryFields | []string | fields | No | Internal use only |
| OqlQuery | string | oqlQuery | No | Internal use only |

---

#### 64. CONVERTED_QUERY
**File:** `playbook.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Query | string | query | Yes | OQL result |
| Fields | []string | fields | No | Visible fields |

---

#### 65. QUERY_TERM
**File:** `query.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Raw | string | - | Yes | Term content |
| Quoted | bool | - | Yes | Whether quoted |
| Quote | rune | - | No | Quote character (' or ") |
| Grouped | bool | - | Yes | Whether grouped with () |

**Validation:**
- Raw cannot be empty (whitespace trimmed)

---

#### 66. QUERY_SEGMENT (Interface)
**File:** `query.go`

**Implementations:**
- `SearchSegment`
- `GroupBySegment`
- `TableSegment`
- `SortBySegment`

**Methods:**
- `String()`: Returns segment as string
- `Kind()`: Returns segment type

**Segment Kind Constants:**
- `SegmentKind_Search = "search"`
- `SegmentKind_GroupBy = "groupby"`
- `SegmentKind_SortBy = "sortby"`
- `SegmentKind_Table = "table"`

---

#### 67. BASE_SEGMENT
**File:** `query.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| terms | []*QueryTerm | - | Yes | Internal use |

**Methods:**
- `Terms()`: Returns term list
- `Clear()`: Clears all terms
- `RemoveTermsWith(raw string)`: Removes terms matching substring, returns count
- `RawFields()`: Returns term Raw values
- `Fields()`: Returns formatted term strings
- `AddField(field string)`: Adds field with auto-quoting

---

#### 68. SEARCH_SEGMENT
**File:** `query.go`
**Inherits:** BaseSegment

**Methods:**
- `AddFilter(field, value, scalar, inclusive, condense bool)`: Complex filter addition with term consolidation

**Filter Constants:**
- `FILTER_INCLUDE = "INCLUDE"`
- `FILTER_EXCLUDE = "EXCLUDE"`
- `FILTER_EXACT = "EXACT"`
- `FILTER_DRILLDOWN = "DRILLDOWN"`

---

#### 69. GROUP_BY_SEGMENT
**File:** `query.go`
**Inherits:** BaseSegment

No additional fields.

---

#### 70. TABLE_SEGMENT
**File:** `query.go`
**Inherits:** BaseSegment

No additional fields.

---

#### 71. SORT_BY_SEGMENT
**File:** `query.go`
**Inherits:** BaseSegment

No additional fields.

---

#### 72. QUERY
**File:** `query.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Segments | []QuerySegment | - | Yes | None |

**Methods:**
- `Parse(str string)`: Parses query string into segments (complex state machine)
- `NamedSegment(name string)`: Gets first segment of type
- `NamedSegments(name string)`: Gets all segments of type
- `AddSegment(segment)`: Appends segment
- `RemoveSegment(name string)`: Removes and returns first segment of type
- `String()`: Renders query as string with " | " separators
- `Filter(field, value, scalar, mode, condense)`: Modifies search segment
- `Group(segmentIdx, field)`: Adds groupby segment
- `Sort(field)`: Adds sortby segment
- `Table(field)`: Adds table segment

---

#### 73. QUERY_TASK
**File:** `querytask.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| GridId | string | gridId | No | Subgrid ID |
| TaskId | string | taskId | Yes | Elasticsearch task ID |
| Details | string | details | Yes | Task description |
| StartTime | time.Time | startTime | Yes | None |
| ElapsedMs | int64 | elapsedMs | Yes | None |
| Cancelable | bool | cancelable | Yes | None |
| EsClient | *elasticsearch.Client | - (not serialized) | No | Internal Elasticsearch client |

---

#### 74. REPO
**File:** `repo.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| RepoUrl | string | repo | Yes | URL string |
| Branch | *string | - | No | Git branch |
| License | string | - | No | License type |
| Folder | *string | - | No | Subfolder path |
| Community | bool | - | No | Community flag |
| RulesetName | string | - | No | Ruleset name |

**Validation:**
- RepoUrl is required
- License required based on licenseRequired parameter
- Community parsed from bool, int, or string with ParseBool fallback

---

#### 75. SRV_TOKEN
**File:** `srvtoken.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | None |
| Expiration | time.Time | expiration | Yes | None |
| Hash | []byte | hash | Yes | HMAC SHA-512 |

**Methods:**
- `validate(id)`: Checks ID and expiration
- `GenerateSrvToken(srvKey, id, validSeconds)`: Creates and encodes token with HMAC
- `ValidateSrvToken(srvKey, id, encryptedToken)`: Base64-decodes and validates token

**Custom JSON Marshaling:** Hash is serialized/deserialized as part of token.

---

#### 76. STATUS
**File:** `status.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| GridId | string | gridId | No | Subgrid ID |
| Grid | *GridStatus | grid | No | None |
| Alerts | *AlertsStatus | alerts | No | None |
| Detections | *DetectionsStatus | detections | No | None |

---

#### 77. GRID_STATUS
**File:** `status.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| TotalNodeCount | int | totalNodeCount | Yes | None |
| UnhealthyNodeCount | int | unhealthyNodeCount | Yes | None |
| AwaitingRebootNodeCount | int | awaitingRebootNodeCount | Yes | None |
| Eps | int | eps | Yes | Events per second |

---

#### 78. ALERTS_STATUS
**File:** `status.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| NewCount | int | newCount | Yes | New alerts (unused) |

---

#### 79. DETECTIONS_STATUS
**File:** `status.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| ElastAlert | *EngineState | elastalert | No | None |
| Suricata | *EngineState | suricata | No | None |
| Strelka | *EngineState | strelka | No | None |

---

#### 80. ENGINE_STATE
**File:** `status.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| IntegrityFailure | bool | integrityFailure | Yes | None |
| Migrating | bool | migrating | Yes | None |
| MigrationFailure | bool | migrationFailure | Yes | None |
| Importing | bool | importing | Yes | None |
| Syncing | bool | syncing | Yes | None |
| SyncFailure | bool | syncFailure | Yes | None |
| Blocked | bool | blocked | Yes | None |

**Methods:**
- `IsFailureState()`: Returns true if any failure flag is true

---

#### 81. SUBGRID
**File:** `subgrid.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | Must not be empty |
| ManagerUrl | string | managerUrl | Yes | Must be HTTPS, cannot be empty |
| ClientId | string | clientId | Yes | Must start with API_CLIENT_PREFIX |
| ClientSecret | string | clientSecret | Yes | Must not be empty; masked on marshal |
| Enabled | bool | enabled | Yes | None |
| CaCertificate | string | caCertificate | No | PEM format |
| SkipTlsVerify | bool | skipTlsVerify | Yes | Useful for test environments |
| AccessToken | string | - (transient) | No | Ephemeral Bearer token |
| TokenExpiration | time.Time | - (transient) | No | Token expiry timestamp |

**Methods:**
- `Verify()`: Validates all fields
- `MarshalJSON()`: Masks ClientSecret on output
- `getHttpsClient()`: Creates TLS client with CA/SkipTlsVerify support
- `refreshAccessToken()`: OAuth2 client_credentials flow
- `MakeApiCall(method, url, body, headers)`: Makes authenticated API call to subgrid
- `GetGridNodes()`: Retrieves nodes from subgrid
- `GetGridStatus()`: Retrieves status from subgrid

**Validation:**
- Enabled subgrids require all fields non-empty
- ManagerUrl must start with "https://"
- ClientId must start with "socl_"

---

#### 82. TOOL_REQUEST
**File:** `tool.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| SessionId | string | sessionId | Yes | Chat session ID |
| ToolUseId | string | toolUseId | Yes | Unique tool use identifier |
| Params | json.RawMessage | params | Yes | JSON parameters |
| Model | string | model, omitempty | No | Model to use |
| AuxData | json.RawMessage | auxData, omitempty | No | Tool-specific data |

---

#### 83. TOOL_RESPONSE
**File:** `tool.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| ToolName | string | - | Yes | None |
| Parameters | any | - | Yes | None |
| Result | any | - | Yes | None |
| TimeToExecute | time.Duration | - | Yes | None |
| OnBehalfOfUser | string | - | No | None |

---

#### 84. TOOL_CONFIG
**File:** `tool.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Tools | []*ToolSpec | tools | No | None |
| ToolChoice | map[string]JSONSchema | toolChoice | No | None |

---

#### 85. TOOL_SPEC
**File:** `tool.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Spec | ToolDefinition | toolSpec | Yes | None |

---

#### 86. TOOL_DEFINITION
**File:** `tool.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name | Yes | None |
| Description | string | description | Yes | None |
| InputSchema | JSONSchema | inputSchema | Yes | None |

---

#### 87. JSON_SCHEMA
**File:** `tool.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Json | *ToolSchema | json, omitempty | No | None |

---

#### 88. TOOL_SCHEMA
**File:** `tool.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Type | string | type | Yes | None |
| Properties | map[string]ToolSchemaProperty | properties | Yes | None |
| Required | []string | required, omitempty | No | None |

---

#### 89. TOOL_SCHEMA_PROPERTY
**File:** `tool.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Type | string | type | Yes | None |
| Description | string | description | Yes | None |
| Default | any | default, omitempty | No | None |
| Items | map[string]ToolSchemaProperty | items, omitempty | No | For array types |

---

#### 90. UNAUTHORIZED
**File:** `unauthorized.go`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| CreateTime | time.Time | - | Yes | Set at creation |
| Subject | string | - | Yes | User/client ID |
| Operation | string | - | Yes | Action attempted |
| Target | string | - | Yes | Resource target |

**Methods:**
- `Error()`: Implements error interface with formatted string

---

#### 91. USER
**File:** `user.go`

**Constants:**
- `MAX_EMAIL_LEN = 100`
- `MAX_FIRSTNAME_LEN = 100`
- `MAX_LASTNAME_LEN = 100`
- `MAX_NOTE_LEN = 100`
- `MAX_ROLE_LEN = 50`
- `MAX_USER_ID_LEN = 36`
- `MAX_SEARCH_USERNAME_LEN = 50`

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | Yes | Max 36 chars (UUID) |
| CreateTime | time.Time | createTime | Yes | Read-only |
| UpdateTime | time.Time | updateTime, omitempty | No | Read-only |
| Email | string | email | Yes | Max 100 chars |
| FirstName | string | firstName | No | Max 100 chars |
| LastName | string | lastName | No | Max 100 chars |
| TotpStatus | string | totpStatus | No | Read-only (enabled/disabled/etc) |
| OidcStatus | string | oidcStatus | No | Read-only |
| WebauthnStatus | string | webauthnStatus | No | Read-only (beta) |
| Note | string | note | No | Max 100 chars |
| Roles | []string | roles | No | Each max 50 chars |
| Status | string | status | No | locked, active, etc |
| SearchUsername | string | searchUsername | No | Elasticsearch username, max 50 chars |
| Password | string | password | No | 8-72 chars, no: ' " $ \ |
| PasswordChanged | bool | passwordChanged | No | Read-only (imperfect detector) |

**Validation Methods:**
- `Verify()`: Checks all field length constraints

---

### INCOMING MESSAGE TYPES (Assistant Chat)
**File:** `assistant.go`

#### INCOMING_MESSAGE
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Msg | string | msg | Yes | Message content |
| SessionId | string | sessionId | Yes | Can be empty for new session |
| Model | string | model, omitempty | No | Model name |
| Tags | []string | tags, omitempty | No | Message tags |

---

#### CHAT_REQUEST
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Messages | []*Message | messages | Yes | None |
| MaxTokens | int | max_tokens, omitempty | No | None |
| Temperature | float64 | temperature, omitempty | No | None |
| TopP | float64 | top_p | No | None |
| TopK | int | top_k | No | None |
| StopSequences | []string | stop_sequences, omitempty | No | None |
| System | string | system, omitempty | No | System prompt override |
| Stream | bool | stream, omitempty | No | None |
| ToolConfig | json.RawMessage | toolConfig, omitempty | No | Tool definitions |
| UserId | string | user_uuid, omitempty | No | User identifier |
| SystemAppend | string | system_append, omitempty | No | Additional context |
| Model | string | model, omitempty | No | Model specification |

---

#### STORED_MESSAGE
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Tags | []string | tags, omitempty | Yes | None |
| SessionId | string | session_id | Yes | None |
| Model | string | model, omitempty | No | None |
| Message | *Message | message | Yes | None |

**Custom JSON Marshaling:** Marshals Message field using saveableMessage struct to flatten content representation.

**saveableMessage Structure:**
- Id, Role, ContentStr, ContentBlocks, Thoughts, StopReason, StopSequence, Usage

---

#### MESSAGE
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Id | string | id | No | Optional UUID |
| Role | string | role | Yes | "user" or "assistant" |
| ContentStr | string | - (transient) | No | Plain text content |
| ContentBlocks | []ContentBlock | - (transient) | No | Structured content |
| Thoughts | string | thoughts, omitempty | No | Model reasoning |
| StopReason | *string | stop_reason, omitempty | No | e.g., "user_request" |
| StopSequence | *string | stop_sequence, omitempty | No | e.g., "end_turn" |
| Usage | *Usage | usage, omitempty | No | Token statistics |

**Custom JSON Marshaling:** Handles flexible content representation (string OR array of ContentBlocks).

---

#### CONTENT_BLOCK
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Type | string | type, omitempty | No | text, tool_request, etc |
| Id | string | id, omitempty | No | Block identifier |
| Name | string | name, omitempty | No | e.g., "tool_use" |
| Input | json.RawMessage | input, omitempty | No | Tool input parameters |
| Json | any | json, omitempty | No | Structured content |
| Content | any | content, omitempty | No | Dynamic content |
| Text | string | text, omitempty | No | Plain text |
| ToolResult | *ToolResult | toolResult, omitempty | No | None |
| ThoughtSignature | []byte | thought_signature, omitempty | No | Reasoning signature |

---

#### TOOL_RESULT
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Name | string | name, omitempty | No | Tool name |
| ToolUseId | string | toolUseId | Yes | Reference to tool use |
| Content | []ToolResultContent | content | Yes | Result content |
| Status | string | status, omitempty | No | Result status |
| IsError | bool | isError, omitempty | No | Error flag |

---

#### TOOL_RESULT_CONTENT
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Json | any | json, omitempty | No | Structured result |
| Text | string | text, omitempty | No | Text result |

---

#### USAGE
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| InputTokens | int | input_tokens | Yes | None |
| OutputTokens | int | output_tokens | Yes | None |
| Credits | int | credits | Yes | Remaining balance |

---

#### BALANCE_RESPONSE
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| KeyId | string | api_key_prefix | No | API key identifier |
| CompanyId | string | company_id, omitempty | No | Organization ID |
| Status | string | status, omitempty | No | Key status |
| Balance | int64 | credit_balance, omitempty | No | Credit balance |
| HealthStatus | string | health_status, omitempty | No | Service health |

---

#### HEALTH_RESPONSE
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Status | string | status | Yes | healthy, unhealthy, etc |

---

#### ASSISTANT_SESSION
**Inherits:** Auditable

| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Title | string | title | Yes | Session title |
| SessionId | string | sessionId | Yes | Unique identifier |
| DeleteTime | *time.Time | deleteTime, omitempty | No | Deletion timestamp |
| Type | string | type, omitempty | No | e.g., "alert_investigation" |
| EntityId | string | entityId, omitempty | No | Associated entity ID |
| Tags | []string | tags | Yes | Session tags |
| Usage | *SessionUsage | usage, omitempty | No | None |

---

#### ASSISTANT_SESSION_DETAILS
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Session | *AssistantSession | session | Yes | None |
| History | []*StoredMessage | history | Yes | None |

---

#### MODEL_USAGE_STATS
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| ModelInputTokens | int | modelInputTokens | Yes | None |
| ModelOutputTokens | int | modelOutputTokens | Yes | None |
| ModelCredits | int | modelCredits | Yes | None |
| ModelMessages | int | modelMessages | Yes | None |

---

#### SESSION_USAGE
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| TotalInputTokens | int | totalInputTokens | Yes | None |
| TotalOutputTokens | int | totalOutputTokens | Yes | None |
| TotalCredits | int | totalCredits | Yes | None |
| TotalMessages | int | totalMessages | Yes | None |
| ModelUsage | map[string]*ModelUsageStats | modelUsage, omitempty | No | Per model@adapter |

---

#### USER_USAGE
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| UserId | string | userId | Yes | None |
| TotalInputTokens | int | totalInputTokens | Yes | None |
| TotalOutputTokens | int | totalOutputTokens | Yes | None |
| TotalCredits | int | totalCredits | Yes | None |
| TotalSessions | int | totalSessions | Yes | None |
| TotalMessages | int | totalMessages | Yes | None |
| ModelUsage | map[string]*ModelUsageStats | modelUsage, omitempty | No | None |

---

#### UPDATE_SESSION_REQUEST
| Field | Go Type | JSON Key | Required? | Validation |
|-------|---------|----------|-----------|------------|
| Action | string | action | Yes | enum: add, remove |
| Tag | string | tag | Yes | Tag to add/remove |

---

#### GET_SESSIONS_OPTS
**Options Pattern Implementation** - All fields private with getter methods:

| Field | Go Type | Getter Method | Default |
|-------|---------|---------------|---------|
| includeDeleted | bool | IncludeDeleted() | false |
| userId | string | UserId() | "" |
| sessionId | string | SessionId() | "" |
| usage | bool | Usage() | false |
| start | time.Time | Range() (returns start, end) | zero |
| end | time.Time | Range() (returns start, end) | zero |

**Option Functions:**
- `GetSessionsWithIncludeDeleted(bool)`
- `GetSessionsWithUserId(string)`
- `GetSessionsWithSessionId(string)`
- `GetSessionsWithRange(start, end time.Time)`
- `GetSessionsWithUsage(bool)`

**Constant:**
- `MessageTagContextCompression = "context_compression"`

---

## KEY VALIDATION RULES SUMMARY

### Field Length Constraints
- Client ID: max 55 chars
- Client Name: max 50 chars
- Permission: max 50 chars
- User ID: max 36 chars
- Email: max 100 chars
- FirstName/LastName: max 100 chars
- Note: max 100 chars
- Role: max 50 chars
- SearchUsername: max 50 chars
- Setting ID: regex `^[a-zA-Z0-9\*\/:_.-]+$`
- Minion ID: regex `^[a-zA-Z0-9_.-]+$`

### Detection Validation
- Engine must be in EnginesByName map
- All overrides must pass Validate() per engine type
- Suricata: supports Modify, Suppress, Threshold
- ElastAlert: supports CustomFilter only
- Regex patterns must compile
- IP addresses must be CIDR format or Suricata variables
- Count/Seconds must be > 0

### Custom Ruleset Validation
- Either `File` OR (`Url` + `TargetFile`) required
- License required
- File extension should be `.rules`

### Subgrid Validation
- If enabled: all fields must be non-empty
- ManagerUrl must start with "https://"
- ClientId must start with "socl_"

### Password Constraints (User)
- 8-72 characters
- Cannot contain: ' " $ \

---

This specification includes every struct, every field, all validation rules, all enums/constants, all custom marshaling logic, and all business methods. The Python developer now has a complete reference for the domain model layer.