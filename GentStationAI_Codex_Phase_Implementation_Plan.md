# GentStationAI Codex Phase Implementation Plan

Pre-Production Workflow, User Management, Onboarding, Reporting, and Production Readiness Follow-Up

Prepared for: Branislav Radomirovic
Role perspective: Senior Developer / Senior Architect
Purpose: A Codex-ready phased implementation plan based on the latest pre-production status report. The plan is designed so you can present it, track it, and execute it phase by phase without mixing unrelated changes.

---

## 1. Executive direction

GentStationAI should now move from generic pre-production fixes into a controlled implementation sequence focused on workflow correctness. The highest priority is not adding new AI capabilities. The highest priority is proving that the business workflow works every day for every role:

- Employee receives a personal report for their own video submissions.
- Gas Station Manager receives accumulated station reports for all employees in the station.
- Region Manager receives consolidated reports from all stations in the region.
- General Manager receives comprehensive tenant/company reports.
- The same reporting hierarchy works for daily, weekly, and monthly cumulative reports.
- Report schedules and delivery channels can be changed without code changes.
- Tier 1 onboarding works as Telegram-first onboarding.
- Tier 2 onboarding works as platform + CCTV onboarding.

Because this is pre-production, credential rotation can remain a production release gate. Do not let Codex spend the next sprint rotating credentials unless the environment becomes public or real customer data is loaded.

---

## 2. Implementation principles for Codex

Codex must follow these rules for every phase:

1. Implement one phase only. Do not jump ahead.
2. Inspect current code before changing it.
3. Preserve current Tier 1 behavior unless a task explicitly changes it.
4. Add or update tests for every workflow change.
5. Use explicit `tenant_id` filters in all operational and reporting queries.
6. Use central helpers for tenant context, role scope, feature gates, and report schedules.
7. Do not hard-code report times, old Render URLs, or production credentials.
8. Keep pre-production and production settings separate.
9. Produce an implementation summary after every phase: files changed, tests run, known risks, and next phase readiness.

---

## 3. Recommended phase sequence

| Phase | Name | Priority | Outcome | Can be demoed? |
|---:|---|---|---|---|
| 0 | Pre-production workflow hotfixes | P0 | Reset URL, reset UX, onboarding import, activation context fixed | Yes |
| 1 | Reporting model and tenant-safe query foundation | P0 | Employee scope, tenant filters, schedule/subscription tables | Partly |
| 2 | Full report builder and scheduler hierarchy | P0 | Daily/weekly/monthly reports for Employee, Station, Region, Company | Yes |
| 3 | Report administration and delivery observability | P1 | Schedule UI, test-send action, delivery attempts | Yes |
| 4 | User management hardening | P1 | Role validation, lifecycle states, bulk import, Telegram status | Yes |
| 5 | Tier 1 Telegram onboarding | P1 | Telegram-first customer onboarding SOP and in-product checklist | Yes |
| 6 | Tier 2 platform + CCTV onboarding | P1 | CCTV onboarding, camera/zone/reviewer checklist, sample processing readiness | Yes |
| 7 | Cross-tenant, role-scope, and regression tests | P0/P1 | Automated confidence that reports and scopes are safe | No, but required |
| 8 | Pre-production pilot release package | P1 | Dry-run package for 3-5 stations and operational handoff | Yes |
| 9 | Production release hardening gate | P0 before prod | Credential rotation, repo cleanup, deployment exposure, backup/restore | Yes |

---

## 4. Phase 0 - Pre-production workflow hotfixes

### Objective
Fix the current user-facing defects that can block pre-production testing: wrong reset URL, misleading reset wording, false error after reset mail delivery, onboarding import bug, and activation email context issue.

### Codex tasks
1. Inspect `core/comm_service.py`, password reset UI page, and environment config loading.
2. Add `APP_LOGIN_URL` to pre-production env template and documentation.
3. Replace old Render fallback in `_login_url()` with environment-aware logic:
   - use configured `APP_LOGIN_URL` when present;
   - fail loudly in `production`, `preprod`, or `staging`;
   - allow `http://localhost:8501/` only for local development.
4. Fix reset UX consistency:
   - fast pre-production option: rename button/email to temporary password; or
   - preferred option: implement real token reset in Phase 0 only if small enough.
5. Separate SMTP delivery from audit logging so email success is not reported as failure when audit logging fails.
6. Prevent password lockout where possible; at minimum document that token-based reset is required for production.
7. Fix `core/platform_admin.py` missing `create_user` import.
8. Fix activation email from platform onboarding by passing tenant context explicitly or providing a platform-safe activation function.
9. Add regression tests or smoke tests for reset URL, reset send result, tenant onboarding, and activation email generation.

### Acceptance criteria
- Reset email uses the pre-production URL, not Render.
- UI wording matches actual reset behavior.
- No false error appears if SMTP accepts the reset email.
- Platform Admin can create a tenant and first General Manager without `NameError`.
- Activation email works when tenant is created from platform context.
- Tests or documented smoke checks are included.

### Codex prompt
```text
Implement Phase 0 only. Fix pre-production workflow blockers: APP_LOGIN_URL handling, old Render reset URL fallback, password reset false-error behavior, reset UI wording, Platform Admin create_user import, and activation email tenant context. Do not implement reporting tables or onboarding checklists in this phase. Add focused tests or smoke checks and report files changed, tests run, and remaining risks.
```

---

## 5. Phase 1 - Reporting model and tenant-safe query foundation

### Objective
Create the data and code foundation for configurable reporting and safe report generation. This phase does not need to perfect all templates yet; it must make reporting tenant-safe and extensible.

### Codex tasks
1. Inspect `core/report_builder.py`, `core/report_scheduler.py`, database schema, and existing scheduled report tables.
2. Add explicit `tenant_id` filtering to every report query, including station manager immediate AI report lookup.
3. Add `employee` scope support to report builder queries using `sub.employee_id`.
4. Ensure zero-activity station/region/company/employee reports still display correct scope names.
5. Add migration for:
   - `report_schedules`;
   - `report_subscriptions`;
   - `report_delivery_attempts`.
6. Add indexes for `tenant_id`, `scope_type`, `scope_id`, `recipient_user_id`, `enabled`, `report_type`, and delivery timestamps.
7. Add seed/default schedule creation for a tenant:
   - Employee daily;
   - Station Manager daily;
   - Region Manager daily;
   - General Manager daily;
   - Weekly cumulative;
   - Monthly cumulative.
8. Add unit/database tests proving reports cannot cross tenant boundaries.

### Acceptance criteria
- Report builder supports `employee`, `station`, `region`, and `company` scopes.
- Every report query explicitly filters by `tenant_id`.
- Report schedules/subscriptions/delivery attempts exist and migrate cleanly.
- Default schedules can be seeded for a tenant.
- Cross-tenant report leakage tests pass.

### Codex prompt
```text
Implement Phase 1 only. Add tenant-safe reporting foundation: explicit tenant_id filters in all report queries, employee report scope, zero-activity scope names, migrations for report_schedules/report_subscriptions/report_delivery_attempts, default schedule seeding, indexes, and cross-tenant report tests. Do not build the full schedule UI yet.
```

---

## 6. Phase 2 - Full report builder and scheduler hierarchy

### Objective
Implement the required business reporting hierarchy for daily, weekly, and monthly reports.

### Codex tasks
1. Refactor scheduler to read from `report_schedules` and `report_subscriptions` instead of hard-coded role derivation only.
2. Generate report recipients for:
   - Employee personal reports;
   - Gas Station Manager station reports;
   - Region Manager region reports;
   - General Manager company reports.
3. Implement daily, weekly, and monthly cumulative date windows.
4. Respect tenant timezone and configured send time.
5. Add configurable weekly day and monthly day/last-day behavior.
6. Add report templates for each scope:
   - employee personal;
   - station rollup;
   - region consolidated;
   - general manager executive summary.
7. Add missing-submission logic for employees and stations.
8. Add delivery through configured channels: email, Telegram, or both.
9. Add delivery attempt records for each channel.
10. Add manual test-run mode that generates reports without waiting for schedule time.

### Acceptance criteria
- Employee receives personal daily report based only on own submissions.
- Station Manager receives accumulated station report.
- Region Manager receives consolidated regional report.
- General Manager receives comprehensive company report.
- Weekly and monthly cumulative reports generate correct date ranges.
- Schedule timing is configurable per tenant.
- Delivery attempts are recorded per recipient and channel.
- No report includes data from another tenant.

### Codex prompt
```text
Implement Phase 2 only. Build the complete reporting hierarchy using the reporting model from Phase 1. Reports must support employee, station, region, and company scopes; daily, weekly, and monthly cadences; tenant timezone; configurable schedule; configured delivery channels; delivery attempt logging; and manual test-run mode. Preserve existing report behavior where compatible.
```

---

## 7. Phase 3 - Report administration and delivery observability

### Objective
Give admins a practical way to configure schedules, run test reports, and troubleshoot delivery.

### Codex tasks
1. Create tenant admin UI for report schedules:
   - daily enabled/disabled;
   - weekly enabled/disabled and day;
   - monthly enabled/disabled and day/last day;
   - send time;
   - timezone;
   - channels;
   - recipient overrides.
2. Add recipient subscription UI for users and scopes.
3. Add `Send test report now` action for daily/weekly/monthly and each scope.
4. Add support/admin view for delivery attempts:
   - recipient;
   - report type;
   - channel;
   - status;
   - error message;
   - attempted timestamp.
5. Add safe retry action for failed delivery attempts.
6. Add audit logs for schedule changes, subscription changes, test sends, and retries.

### Acceptance criteria
- Tenant admin can change report schedules without code changes.
- Admin can trigger test reports manually.
- Support can see whether email and Telegram delivery succeeded or failed.
- Failed report deliveries can be retried safely.
- Schedule changes are audited.

### Codex prompt
```text
Implement Phase 3 only. Build the report administration UI and delivery observability: tenant schedule configuration, recipient subscriptions, Send test report now, delivery-attempt view, retry failed delivery, and audit logging. Do not change Tier 1 or Tier 2 onboarding flows yet.
```

---

## 8. Phase 4 - User management hardening

### Objective
Make the user hierarchy reliable enough for customer onboarding and reporting.

### Codex tasks
1. Add or confirm user lifecycle states: `invited`, `active`, `suspended`, `offboarded`, `password_reset_required`.
2. Add strict assignment validation:
   - employee must have station and manager;
   - Gas Station Manager must have station and region/manager relationship;
   - Region Manager must have region and General Manager relationship;
   - General Manager belongs to tenant/company scope;
   - no cross-tenant station/region assignment.
3. Add bulk import template for users with role, email, station, region, manager, phone, and optional Telegram fields.
4. Add import preview and validation result before commit.
5. Add user status dashboard:
   - invited;
   - active;
   - Telegram linked;
   - first video received;
   - last submission date;
   - missing manager/station/region;
   - suspended/offboarded.
6. Add audit logs for user creation, assignment changes, suspension, offboarding, and bulk import.

### Acceptance criteria
- Invalid hierarchy assignments are blocked.
- Bulk import catches errors before creating users.
- Admin can clearly see which users are ready for reporting and Telegram use.
- User status is tenant-scoped.
- User lifecycle actions are audited.

### Codex prompt
```text
Implement Phase 4 only. Harden user management: lifecycle states, strict role/station/region/manager validation, no cross-tenant assignments, bulk import template with preview validation, user onboarding status dashboard, Telegram-linked status, and audit logs. Do not build Tier 1/Tier 2 onboarding checklists yet except where needed to support user status.
```

---

## 9. Phase 5 - Tier 1 Telegram onboarding

### Objective
Create a dedicated Tier 1 onboarding process for customers using Telegram Bot as the primary employee interface.

### Codex tasks
1. Create Tier 1 onboarding checklist page or admin workflow.
2. Include steps for:
   - tenant setup;
   - timezone and report language;
   - regions and stations;
   - manager hierarchy;
   - employee import;
   - Telegram activation links;
   - station QR instructions;
   - test video submission;
   - report validation.
3. Generate per-user Telegram activation links.
4. Add linked/unlinked Telegram dashboard.
5. Add first-video test status per employee and per station.
6. Add missing daily submission alert configuration.
7. Add Tier 1 customer handoff document in `docs/onboarding/tier1_telegram.md`.
8. Add test/dry-run checklist for pre-production pilots.

### Acceptance criteria
- A Tier 1 tenant can be onboarded without CCTV setup.
- Every employee has a clear Telegram linking path.
- Admin can see Telegram linked/unlinked status.
- Each station can complete a test submission.
- Reports can be validated for every role after test submissions.
- Tier 1 onboarding documentation exists.

### Codex prompt
```text
Implement Phase 5 only. Build Tier 1 Telegram-first onboarding: tenant/station/user checklist, Telegram activation links, linked/unlinked dashboard, first-video test status, missing submission alert settings, report validation step, and docs/onboarding/tier1_telegram.md. Do not implement CCTV onboarding in this phase.
```

---

## 10. Phase 6 - Tier 2 platform + CCTV onboarding

### Objective
Create a dedicated Tier 2 onboarding process for platform and CCTV customers.

### Codex tasks
1. Create Tier 2 onboarding checklist page or admin workflow.
2. Include steps for:
   - tenant setup as Tier 2;
   - camera/storage limits;
   - platform user login validation;
   - CCTV feature gate validation;
   - reviewer and escalation contacts;
   - camera registry;
   - zone configuration;
   - responsible AI/privacy acceptance;
   - sample clip processing;
   - review center validation;
   - Tier 2 report validation.
3. Add camera import template.
4. Add zone setup checklist and validation.
5. Add CCTV worker to production compose profile or pre-production profile if not already included.
6. Add sample clip/manual job processing test.
7. Add Review Center training checklist.
8. Add docs/onboarding/tier2_cctv.md.

### Acceptance criteria
- Tier 2 onboarding checklist exists and is tenant-scoped.
- Camera/zone setup status is visible.
- CCTV worker can be enabled and health-checked in pre-production.
- Sample CCTV event can be processed and reviewed.
- Tier 2 reports include CCTV section only for Tier 2 tenants.
- Tier 1 tenant cannot access CCTV onboarding or CCTV reports.

### Codex prompt
```text
Implement Phase 6 only. Build Tier 2 platform + CCTV onboarding: checklist UI, camera import template, zone setup validation, reviewer/escalation setup, responsible AI/privacy acceptance, CCTV worker compose/profile enablement, sample clip processing test, Review Center training checklist, and docs/onboarding/tier2_cctv.md. Keep Tier 1 behavior intact and gated.
```

---

## 11. Phase 7 - Cross-tenant, role-scope, and regression tests

### Objective
Add automated confidence that the workflow is safe, especially around reporting and user scope.

### Codex tasks
1. Add test tenants: one Tier 1 and one Tier 2.
2. Add users for every role in each tenant.
3. Add submissions across employees, stations, and regions.
4. Test report generation for every role and cadence.
5. Test direct ID guessing across tenants for report, user, station, region, submission, CCTV event.
6. Test Tier 1 cannot access CCTV onboarding/pages/reports.
7. Test Tier 2 can access CCTV onboarding/pages/reports.
8. Test password reset uses configured URL.
9. Test platform onboarding creates tenant/admin and activation email without tenant context failure.
10. Add a single command or script for pre-production regression checks.

### Acceptance criteria
- Cross-tenant report leakage tests pass.
- Role-scope visibility tests pass.
- Password reset tests pass.
- Tier gate tests pass.
- Pre-production regression command is documented.

### Codex prompt
```text
Implement Phase 7 only. Add comprehensive regression tests for tenant isolation, role scope, report generation, report delivery, password reset URL, platform onboarding activation, Tier 1/Tier 2 gates, and direct ID guessing. Add a documented pre-production regression command. Do not add new features unless required to make tests pass.
```

---

## 12. Phase 8 - Pre-production pilot release package

### Objective
Prepare the system for a controlled pre-production pilot with internal/test users or a limited non-production client group.

### Codex tasks
1. Create `docs/preprod/PILOT_RUNBOOK.md`.
2. Create 3-5 station pilot checklist.
3. Add test data reset/seed script for demo/pilot tenants.
4. Add pre-production deployment checklist:
   - APP_LOGIN_URL configured;
   - SMTP test passed;
   - Telegram bot test passed;
   - report test-send passed;
   - backup job tested;
   - health check passed.
5. Add onboarding completion report export.
6. Add known limitations document for pre-production:
   - credentials not yet rotated;
   - no real customer data;
   - CCTV results estimated/suspected;
   - production hardening pending.
7. Add sign-off template for pilot readiness.

### Acceptance criteria
- Pilot can be executed from documentation without developer explanation.
- Pre-production limitations are explicit.
- Demo/pilot data can be reset and recreated.
- All role reports can be verified before pilot start.
- Onboarding completion can be exported or shown to stakeholders.

### Codex prompt
```text
Implement Phase 8 only. Create the pre-production pilot release package: pilot runbook, 3-5 station checklist, demo/pilot tenant seed-reset script, deployment checklist, onboarding completion export, known limitations, and pilot sign-off template. Do not perform production credential rotation in this phase.
```

---

## 13. Phase 9 - Production release hardening gate

### Objective
Convert the pre-production system into a production-ready deployment candidate. This phase is a hard gate before real customers or real customer data.

### Codex tasks
1. Remove real env files from repository/package.
2. Add `PREPRODUCTION_SECRET_ROTATION_REQUIRED.md` and convert it into completed production checklist.
3. Rotate:
   - Telegram bot token;
   - SMTP/Gmail app password;
   - DB password;
   - app/session secrets;
   - any API keys.
4. Remove `__MACOSX`, `__pycache__`, `.pytest_cache`, local dumps, and generated artifacts from package.
5. Add or strengthen `.gitignore` and `.dockerignore`.
6. Fix production compose exposure:
   - only reverse proxy exposes 80/443;
   - web not directly exposed publicly;
   - Postgres/Redis/Ollama private;
   - CCTV worker profile documented.
7. Verify PostgreSQL version compatibility with dump/restore path.
8. Run backup and restore test.
9. Run full tenant isolation regression suite.
10. Run Tier 1 and Tier 2 onboarding dry-runs.
11. Create production release notes and rollback plan.

### Acceptance criteria
- No real credentials remain in repo/package.
- All production credentials are rotated.
- Only reverse proxy is public.
- Backup and restore test passes.
- Full regression suite passes.
- Production release checklist is signed off.

### Codex prompt
```text
Implement Phase 9 only. Execute the production hardening gate: remove real env files and generated artifacts, rotate production credentials, harden ignore files, fix production compose exposure, verify PostgreSQL dump/restore compatibility, test backup/restore, run full tenant isolation and onboarding dry-runs, and prepare production release notes plus rollback plan. This phase is required before real customer data or public production launch.
```

---

## 14. Tracking board

| Work item | Phase | Owner | Status | Evidence required |
|---|---:|---|---|---|
| Reset URL uses preprod URL | 0 | Codex/dev | Not started | Reset email screenshot/log |
| Reset false-error fixed | 0 | Codex/dev | Not started | Smoke test result |
| Platform Admin tenant creation fixed | 0 | Codex/dev | Not started | Tenant + GM created |
| Employee report scope implemented | 1 | Codex/dev | Not started | Unit test + sample report |
| Tenant filters added to report queries | 1 | Codex/dev | Not started | SQL/code review + tests |
| Report schedule/subscription tables | 1 | Codex/dev | Not started | Migration applied |
| Daily/weekly/monthly scheduler hierarchy | 2 | Codex/dev | Not started | Test-run reports for all roles |
| Report schedule admin UI | 3 | Codex/dev | Not started | Admin changes schedule |
| Report delivery attempts visible | 3 | Codex/dev | Not started | Delivery log screen |
| User hierarchy validation | 4 | Codex/dev | Not started | Invalid assignments blocked |
| Bulk user import | 4 | Codex/dev | Not started | Import preview/validation |
| Tier 1 Telegram onboarding | 5 | Codex/dev | Not started | Tier 1 checklist complete |
| Tier 2 CCTV onboarding | 6 | Codex/dev | Not started | Tier 2 checklist complete |
| Full regression suite | 7 | Codex/dev | Not started | Test command output |
| Pre-production pilot runbook | 8 | Codex/dev | Not started | Runbook + sign-off |
| Production hardening | 9 | Codex/dev | Not started | Release checklist |

---

## 15. Recommended immediate Codex command

Start with Phase 0. Do not start reporting refactor until reset/onboarding hotfixes are completed and tested.

```text
You are working on the GentStationAI repository. Implement Phase 0 only from the GentStationAI Codex Phase Implementation Plan. Fix APP_LOGIN_URL handling, old Render reset URL fallback, password reset false-error behavior, reset UI wording, Platform Admin create_user import, and activation email tenant context. Keep credentials as-is because this is pre-production; do not rotate them now. Do not implement reporting tables, onboarding checklists, or CCTV changes in this phase. Add focused tests or smoke checks and provide a final summary with files changed, tests run, and remaining risks.
```

---

## 16. Management summary

This plan turns the latest status report into an implementation track that can be followed phase by phase. The first milestone should be a stable pre-production workflow: correct reset URL, stable onboarding, tenant-safe reporting foundation, and full report delivery hierarchy. After that, Tier 1 Telegram onboarding and Tier 2 CCTV onboarding can be hardened. Production hardening, including credential rotation, should remain a final release gate, not a blocker for private pre-production testing.
