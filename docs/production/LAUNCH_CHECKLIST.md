# GentStationAI Production Launch Checklist

Complete this checklist before declaring the Ubuntu deployment production-ready.

## 1. Environment
- [ ] `deploy/env/.env.production` exists only on the server.
- [ ] All placeholder secrets have been replaced.
- [ ] `APP_LOGIN_URL` matches the public URL.
- [ ] Any legacy `APP_BASE_URL` value also matches the same public URL if it is used.
- [ ] Resource limits and thread limits were reviewed and tuned for the host.

## 2. Deployment
- [ ] `./deploy/scripts/deploy.sh` completed successfully.
- [ ] `./deploy/scripts/healthcheck.sh` passes.
- [ ] Schema migrations completed without duplicate-table or ghost-revision errors.
- [ ] Platform Health shows healthy or expected worker states.

## 3. Functional smoke
- [ ] Public landing page renders.
- [ ] Login works for the initial admin.
- [ ] Dashboard loads after login.
- [ ] AI Reports and Settings load without backend errors.
- [ ] Telegram intake test succeeds if enabled.
- [ ] Scheduled report generation path was tested.

## 4. Hardening
- [ ] All pre-production credentials have been rotated before public production launch.
- [ ] Platform Health is accessible only to Platform Superadmins.
- [ ] Cross-tenant DB isolation tests pass.
- [ ] Backup script completed and a restore point exists.
- [ ] Runbooks were reviewed by the deployment owner.

## 5. Release decision
- [ ] Remaining risks were reviewed and accepted.
- [ ] Pilot onboarding checklist is ready for customer rollout.
