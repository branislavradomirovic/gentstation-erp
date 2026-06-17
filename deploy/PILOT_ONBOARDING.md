# GentStationAI Pilot Onboarding Checklist

Use this checklist for each 3-5 station pilot onboarding.

## 1. Platform provisioning
- [ ] Log in as a **Platform Superadmin**.
- [ ] Open **Platform Admin**.
- [ ] Create the tenant with the correct tier:
  - [ ] Tier 1 for AI Daily Operations only
  - [ ] Tier 2 for CCTV Intelligence rollout
- [ ] Create or confirm the tenant’s primary admin user.
- [ ] Verify the tenant can sign in successfully.

## 2. Network and master data setup
- [ ] Create the correct **Region** structure.
- [ ] Create each pilot **Station**.
- [ ] Confirm each station has:
  - [ ] accurate GPS coordinates
  - [ ] correct category
  - [ ] assigned region

## 3. Staff and intake readiness
- [ ] Register station managers and reporting users.
- [ ] Confirm welcome/invite communication was sent.
- [ ] Confirm each pilot station has its QR code distributed.
- [ ] Run one sample Telegram submission per pilot station.

## 4. Tier 2 CCTV setup (only if enabled)
- [ ] Register cameras and stream references.
- [ ] Define zones for entrance, pump, and shop where applicable.
- [ ] Confirm CCTV worker heartbeats appear in **Platform Health**.
- [ ] Process at least one sample CCTV job successfully.

## 5. Pilot acceptance checks
- [ ] Dashboard loads without startup or tenant-context errors.
- [ ] AI Reports show tenant-scoped data only.
- [ ] Tier-gated pages are hidden/blocked for non-entitled tenants.
- [ ] Backup script has been run at least once in the target environment.
- [ ] Launch and smoke checklists are complete before pilot handoff.
