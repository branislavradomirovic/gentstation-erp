from __future__ import annotations

from textwrap import dedent
from urllib.parse import urlencode

import streamlit as st

from core.auth import login_user_streamlit
from core.comm_service import send_password_reset_email
from core.config import LOGIN_DISCLAIMER_HTML
from core.database import get_connection


def _launch_href(**params: str) -> str:
    query = urlencode(params)
    return f"?{query}" if query else "?"


def _clear_launch_params() -> None:
    try:
        st.query_params.clear()
    except Exception:
        for key in ("launch_app", "login_view"):
            try:
                del st.query_params[key]
            except Exception:
                pass


def render_public_site() -> None:
    st.markdown(
        dedent(
            """
        <style>
            html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"] {
                margin: 0 !important;
                padding: 0 !important;
            }
            [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(circle at 12% 18%, rgba(11, 94, 215, 0.18), transparent 18%),
                    radial-gradient(circle at 88% 12%, rgba(14, 165, 233, 0.18), transparent 16%),
                    radial-gradient(circle at 80% 82%, rgba(15, 23, 42, 0.10), transparent 22%),
                    linear-gradient(180deg, #edf3f9 0%, #f8fbfd 42%, #f1f5f9 100%);
            }
            [data-testid="stSidebar"],
            [data-testid="stSidebarCollapsedControl"],
            button[kind="header"],
            [data-testid="collapsedControl"] {
                display: none !important;
            }
            [data-testid="stHeader"], [data-testid="stToolbar"] {
                display: none !important;
            }
            .block-container {
                max-width: 100vw !important;
                padding: 0 !important;
            }
            .standalone-landing {
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                color: #0f172a;
                overflow: hidden;
            }
            .standalone-nav {
                display: flex;
                align-items: center;
                justify-content: space-between;
                width: min(1380px, calc(100vw - 3rem));
                margin: 0 auto;
                padding: 1.35rem 0 0 0;
            }
            .standalone-brand {
                font-size: 1.05rem;
                font-weight: 900;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: #0b5ed7;
            }
            .standalone-nav-links {
                display: flex;
                align-items: center;
                gap: 1.25rem;
                font-size: 0.92rem;
                color: #475569;
            }
            .standalone-link {
                color: inherit;
                text-decoration: none;
            }
            .standalone-shell {
                width: min(1380px, calc(100vw - 3rem));
                margin: 0 auto;
                padding: 2.6rem 0 4.25rem 0;
                display: grid;
                gap: 1.5rem;
            }
            .standalone-hero {
                display: grid;
                grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
                gap: 1.4rem;
                align-items: stretch;
            }
            .standalone-hero-copy {
                position: relative;
                overflow: hidden;
                padding: 2.4rem 2.6rem;
                border-radius: 36px;
                border: 1px solid rgba(148, 163, 184, 0.18);
                background:
                    linear-gradient(140deg, rgba(255,255,255,0.96), rgba(247,250,252,0.92)),
                    linear-gradient(180deg, rgba(11, 94, 215, 0.04), rgba(255,255,255,0));
                box-shadow: 0 28px 65px rgba(15, 23, 42, 0.08);
            }
            .standalone-hero-copy::after {
                content: "";
                position: absolute;
                top: -10%;
                right: -8%;
                width: 280px;
                height: 280px;
                border-radius: 999px;
                background: radial-gradient(circle, rgba(11, 94, 215, 0.12), rgba(11, 94, 215, 0));
                pointer-events: none;
            }
            .standalone-kicker {
                display: inline-flex;
                align-items: center;
                padding: 0.55rem 0.95rem;
                border-radius: 999px;
                background: rgba(11, 94, 215, 0.08);
                color: #0b5ed7;
                font-size: 0.76rem;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 0.11em;
            }
            .standalone-title {
                margin: 1rem 0 0 0;
                font-size: clamp(3.1rem, 6vw, 5.3rem);
                line-height: 0.92;
                font-weight: 900;
                max-width: 10.6ch;
                color: #0f172a;
            }
            .standalone-subtitle {
                margin: 1.25rem 0 0 0;
                max-width: 46rem;
                font-size: 1.05rem;
                line-height: 1.82;
                color: #475569;
            }
            .standalone-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 0.9rem;
                margin-top: 1.8rem;
            }
            .standalone-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 3.25rem;
                padding: 0.9rem 1.35rem;
                border-radius: 999px;
                text-decoration: none;
                font-weight: 800;
                font-size: 0.94rem;
                transition: transform 0.15s ease, box-shadow 0.15s ease;
            }
            .standalone-btn:hover {
                transform: translateY(-1px);
            }
            .standalone-btn-primary {
                background: linear-gradient(135deg, #0b5ed7, #1d4ed8);
                color: #fff;
                box-shadow: 0 18px 36px rgba(29, 78, 216, 0.24);
            }
            .standalone-btn-secondary {
                background: rgba(255,255,255,0.92);
                color: #0f172a;
                border: 1px solid rgba(15, 23, 42, 0.10);
            }
            .standalone-highlight-row {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.9rem;
                margin-top: 1.8rem;
            }
            .standalone-highlight {
                padding: 1rem 1.05rem;
                border-radius: 20px;
                background: rgba(255,255,255,0.76);
                border: 1px solid rgba(148, 163, 184, 0.18);
                backdrop-filter: blur(8px);
            }
            .standalone-highlight-label {
                font-size: 0.76rem;
                font-weight: 900;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #2563eb;
            }
            .standalone-highlight-copy {
                margin-top: 0.45rem;
                font-size: 0.92rem;
                line-height: 1.58;
                color: #475569;
            }
            .standalone-aside {
                border: 1px solid rgba(15, 23, 42, 0.08);
                border-radius: 36px;
                padding: 1.4rem;
                background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,247,251,0.96));
                box-shadow: 0 24px 60px rgba(15, 23, 42, 0.08);
                display: grid;
                gap: 1rem;
            }
            .standalone-aside-card-dark {
                padding: 1.4rem;
                border-radius: 24px;
                background:
                    radial-gradient(circle at top right, rgba(96, 165, 250, 0.16), transparent 28%),
                    linear-gradient(160deg, #0f172a, #1e293b);
                color: #fff;
            }
            .standalone-aside-label {
                font-size: 0.74rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: rgba(191, 219, 254, 0.92);
            }
            .standalone-aside-title {
                margin-top: 0.7rem;
                font-size: 1.26rem;
                font-weight: 800;
                line-height: 1.25;
            }
            .standalone-aside-copy {
                margin-top: 0.6rem;
                font-size: 0.92rem;
                line-height: 1.7;
                color: rgba(255,255,255,0.78);
            }
            .standalone-stat-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 1rem;
            }
            .standalone-stat {
                padding: 1rem 1.05rem;
                border-radius: 20px;
                background: rgba(255,255,255,0.96);
                border: 1px solid rgba(148, 163, 184, 0.16);
                box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
            }
            .standalone-stat-value {
                font-size: 1.18rem;
                font-weight: 900;
                color: #0f172a;
            }
            .standalone-stat-copy {
                margin-top: 0.3rem;
                font-size: 0.85rem;
                line-height: 1.5;
                color: #64748b;
            }
            .standalone-section-grid {
                display: grid;
                grid-template-columns: 1.1fr 0.9fr;
                gap: 1rem;
            }
            .standalone-capability-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 1rem;
            }
            .standalone-panel {
                border-radius: 26px;
                border: 1px solid rgba(15, 23, 42, 0.08);
                background: rgba(255,255,255,0.96);
                box-shadow: 0 18px 40px rgba(15, 23, 42, 0.05);
                padding: 1.4rem;
            }
            .standalone-section-title {
                margin: 0;
                font-size: 1.2rem;
                font-weight: 800;
                color: #111827;
            }
            .standalone-section-copy {
                margin: 0.7rem 0 0 0;
                font-size: 0.92rem;
                line-height: 1.7;
                color: #5b6474;
            }
            .standalone-pillars {
                display: grid;
                gap: 0.8rem;
                margin-top: 1rem;
            }
            .standalone-pillar {
                padding: 1rem;
                border-radius: 18px;
                background: linear-gradient(180deg, rgba(248,250,252,0.98), rgba(255,255,255,0.98));
                border: 1px solid rgba(148, 163, 184, 0.18);
            }
            .standalone-pillar-eyebrow {
                font-size: 0.72rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: #0b5ed7;
            }
            .standalone-pillar-title {
                margin-top: 0.4rem;
                font-size: 0.98rem;
                font-weight: 800;
                color: #0f172a;
            }
            .standalone-pillar-copy {
                margin-top: 0.35rem;
                font-size: 0.87rem;
                line-height: 1.55;
                color: #64748b;
            }
            .standalone-capability {
                padding: 1.2rem;
                border-radius: 22px;
                border: 1px solid rgba(148, 163, 184, 0.18);
                background: rgba(255,255,255,0.95);
                box-shadow: 0 14px 32px rgba(15, 23, 42, 0.04);
            }
            .standalone-capability-title {
                margin: 0.4rem 0 0 0;
                font-size: 1rem;
                font-weight: 800;
                color: #0f172a;
            }
            .standalone-capability-copy {
                margin: 0.5rem 0 0 0;
                color: #5b6474;
                line-height: 1.65;
                font-size: 0.88rem;
            }
            .standalone-tier-stack {
                display: grid;
                gap: 0.8rem;
                margin-top: 1rem;
            }
            .standalone-tier {
                padding: 1rem;
                border-radius: 18px;
                border: 1px solid rgba(15, 23, 42, 0.08);
                background: #fff;
            }
            .standalone-tier.featured {
                background: linear-gradient(180deg, rgba(239,246,255,0.95), rgba(255,255,255,0.98));
                border-color: rgba(11, 94, 215, 0.20);
            }
            .standalone-tier-label {
                font-size: 0.72rem;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: #0b5ed7;
            }
            .standalone-tier-title {
                margin-top: 0.38rem;
                font-size: 1rem;
                font-weight: 800;
                color: #0f172a;
            }
            .standalone-tier-copy {
                margin-top: 0.38rem;
                font-size: 0.87rem;
                line-height: 1.55;
                color: #5b6474;
            }
            .standalone-tier-list {
                margin: 0.7rem 0 0 1rem;
                padding: 0;
                color: #334155;
                font-size: 0.84rem;
                line-height: 1.7;
            }
            .standalone-footer-note {
                padding: 1.15rem 1.2rem;
                border-radius: 22px;
                background: linear-gradient(160deg, #0f172a, #1e293b);
                color: rgba(255,255,255,0.8);
                font-size: 0.9rem;
                line-height: 1.7;
            }
            .standalone-footer-note strong {
                color: #fff;
            }
            .standalone-final-cta {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                padding: 1.35rem 1.4rem;
                border-radius: 26px;
                background: linear-gradient(135deg, rgba(11, 94, 215, 0.09), rgba(14, 165, 233, 0.08));
                border: 1px solid rgba(59, 130, 246, 0.18);
            }
            .standalone-final-cta-copy {
                margin: 0;
                color: #334155;
                line-height: 1.65;
                font-size: 0.94rem;
            }
            @media (max-width: 980px) {
                .standalone-shell {
                    width: min(100vw - 1.1rem, 1380px);
                    padding: 1.3rem 0 2rem 0;
                }
                .standalone-nav {
                    width: min(100vw - 1.1rem, 1380px);
                    padding-top: 1rem;
                }
                .standalone-hero,
                .standalone-section-grid,
                .standalone-stat-grid,
                .standalone-capability-grid,
                .standalone-highlight-row {
                    grid-template-columns: 1fr;
                }
                .standalone-title {
                    max-width: 100%;
                }
                .standalone-hero-copy {
                    padding: 1.6rem 1.2rem;
                }
                .standalone-final-cta {
                    flex-direction: column;
                    align-items: flex-start;
                }
            }
        </style>
        """
        ),
        unsafe_allow_html=True,
    )

    public_site_html = dedent(
        f"""
        <div class="standalone-landing">
            <div class="standalone-nav">
                <div class="standalone-brand">GentStationAI</div>
                <div class="standalone-nav-links">
                    <span>Tier 1 Daily Operations</span>
                    <span>Tier 2 CCTV Intelligence</span>
                    <a class="standalone-link" href="{_launch_href(launch_app='1', login_view='1')}">Application</a>
                </div>
            </div>
            <div class="standalone-shell">
                <div class="standalone-hero">
                    <div class="standalone-hero-copy">
                        <div class="standalone-kicker">Production-ready multi-tenant platform</div>
                        <h1 class="standalone-title">Operational AI for modern fuel retail networks.</h1>
                        <p class="standalone-subtitle">
                            GentStationAI gives operators, regional leaders, and platform owners one secure operating system for
                            daily station reporting, management review, AI-assisted decisions, and phased rollout of CCTV intelligence.
                        </p>
                        <div class="standalone-actions">
                            <a class="standalone-btn standalone-btn-primary" href="{_launch_href(launch_app='1', login_view='1')}">Open Application</a>
                            <a class="standalone-btn standalone-btn-secondary" href="{_launch_href(launch_app='1', login_view='1')}">Login to Workspace</a>
                        </div>
                        <div class="standalone-highlight-row">
                            <div class="standalone-highlight">
                                <div class="standalone-highlight-label">Operator value</div>
                                <div class="standalone-highlight-copy">Replace scattered station updates with one accountable daily operating rhythm.</div>
                            </div>
                            <div class="standalone-highlight">
                                <div class="standalone-highlight-label">Leadership value</div>
                                <div class="standalone-highlight-copy">Give regional and company leadership tenant-safe visibility across stations, regions, and alerts.</div>
                            </div>
                            <div class="standalone-highlight">
                                <div class="standalone-highlight-label">Platform value</div>
                                <div class="standalone-highlight-copy">Start with Tier 1 today and selectively expand into Tier 2 CCTV programs when sites are ready.</div>
                            </div>
                        </div>
                    </div>
                    <div class="standalone-aside">
                        <div class="standalone-aside-card-dark">
                            <div class="standalone-aside-label">Executive Summary</div>
                            <div class="standalone-aside-title">One platform from field evidence to managerial action.</div>
                            <div class="standalone-aside-copy">
                                GentStationAI centralizes station submissions, operational review, AI scoring, and follow-up so issues are surfaced earlier and resolved with more consistency.
                            </div>
                        </div>
                        <div class="standalone-panel" style="padding:1rem 1.05rem;">
                            <div class="standalone-pillar-eyebrow">Rollout model</div>
                            <div class="standalone-pillar-title">Start with Tier 1. Expand only where proven.</div>
                            <div class="standalone-pillar-copy">
                                Launch the daily-operations core first, validate the reporting model, then selectively unlock Tier 2 CCTV programs for advanced sites.
                            </div>
                        </div>
                        <div class="standalone-panel" style="padding:1rem 1.05rem;">
                            <div class="standalone-pillar-eyebrow">Deployment posture</div>
                            <div class="standalone-pillar-title">Postgres-backed operational state</div>
                            <div class="standalone-pillar-copy">
                                Runtime data, reporting, evidence flows, and tenant-scoped operations are designed to live in the database rather than local filesystem persistence paths.
                            </div>
                        </div>
                    </div>
                </div>

                <div class="standalone-stat-grid">
                    <div class="standalone-stat">
                        <div class="standalone-stat-value">1 operating surface</div>
                        <div class="standalone-stat-copy">One application for tenant-isolated daily operations, reporting, administration, and staged expansion.</div>
                    </div>
                    <div class="standalone-stat">
                        <div class="standalone-stat-value">2 rollout tiers</div>
                        <div class="standalone-stat-copy">AI Daily Operations for immediate adoption and CCTV Intelligence for advanced site programs.</div>
                    </div>
                    <div class="standalone-stat">
                        <div class="standalone-stat-value">Private by design</div>
                        <div class="standalone-stat-copy">Role-based access, tenant isolation, and no public exposure of system health, queue state, or internal diagnostics.</div>
                    </div>
                </div>

                <div class="standalone-capability-grid">
                    <div class="standalone-capability">
                        <div class="standalone-pillar-eyebrow">Capability 1</div>
                        <h3 class="standalone-capability-title">Station intake and evidence review</h3>
                        <p class="standalone-capability-copy">Capture operational submissions, media-backed evidence, and follow-up context in one manager-facing workflow.</p>
                    </div>
                    <div class="standalone-capability">
                        <div class="standalone-pillar-eyebrow">Capability 2</div>
                        <h3 class="standalone-capability-title">AI summaries and scheduled reporting</h3>
                        <p class="standalone-capability-copy">Convert raw daily activity into structured station, regional, and company reporting for faster review cycles.</p>
                    </div>
                    <div class="standalone-capability">
                        <div class="standalone-pillar-eyebrow">Capability 3</div>
                        <h3 class="standalone-capability-title">Tenant-safe administration</h3>
                        <p class="standalone-capability-copy">Operate multiple fuel-retail companies on one platform while preserving company, region, and station boundaries.</p>
                    </div>
                    <div class="standalone-capability">
                        <div class="standalone-pillar-eyebrow">Capability 4</div>
                        <h3 class="standalone-capability-title">CCTV expansion path</h3>
                        <p class="standalone-capability-copy">Enable deeper site intelligence only for subscribed tenants and only where the operating model justifies it.</p>
                    </div>
                </div>

                <div class="standalone-section-grid">
                    <div class="standalone-panel">
                        <h2 class="standalone-section-title">The problem</h2>
                        <p class="standalone-section-copy">
                            Fuel retail teams often rely on fragmented reporting, delayed regional feedback, and inconsistent managerial follow-up.
                            Valuable operational evidence arrives too late, risk visibility is weak, and too much coordination happens in ad hoc channels.
                        </p>
                        <div class="standalone-pillars">
                            <div class="standalone-pillar">
                                <div class="standalone-pillar-eyebrow">Pillar 1</div>
                                <div class="standalone-pillar-title">Daily operational visibility</div>
                                <div class="standalone-pillar-copy">Bring submissions, review, AI scoring, alerts, and follow-up into one operating rhythm.</div>
                            </div>
                            <div class="standalone-pillar">
                                <div class="standalone-pillar-eyebrow">Pillar 2</div>
                                <div class="standalone-pillar-title">Tenant-safe scale</div>
                                <div class="standalone-pillar-copy">Serve multiple gas-station companies on one platform without exposing one tenant to another.</div>
                            </div>
                            <div class="standalone-pillar">
                                <div class="standalone-pillar-eyebrow">Pillar 3</div>
                                <div class="standalone-pillar-title">Upgrade path to CCTV intelligence</div>
                                <div class="standalone-pillar-copy">Start with Tier 1 operations today and unlock camera-aware workflows only where the business case is proven.</div>
                            </div>
                        </div>
                    </div>
                    <div class="standalone-panel">
                        <h2 class="standalone-section-title">Tier comparison</h2>
                        <div class="standalone-tier-stack">
                            <div class="standalone-tier">
                                <div class="standalone-tier-label">Tier 1</div>
                                <div class="standalone-tier-title">AI Daily Operations</div>
                                <div class="standalone-tier-copy">Operational reporting, alerts, dashboards, summaries, and manager decision support.</div>
                                <ul class="standalone-tier-list">
                                    <li>Telegram-based station intake</li>
                                    <li>AI reports and scheduler workflows</li>
                                    <li>Regional and station oversight</li>
                                    <li>Fast onboarding for pilot networks</li>
                                </ul>
                            </div>
                            <div class="standalone-tier featured">
                                <div class="standalone-tier-label">Tier 2</div>
                                <div class="standalone-tier-title">CCTV Intelligence</div>
                                <div class="standalone-tier-copy">Camera-aware intelligence workflows for operators ready to extend beyond daily submission review.</div>
                                <ul class="standalone-tier-list">
                                    <li>Everything in Tier 1</li>
                                    <li>Tier-gated CCTV routes and workers</li>
                                    <li>Camera capacity by tenant plan</li>
                                    <li>Advanced site monitoring readiness</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="standalone-footer-note">
                    <strong>Trust &amp; privacy:</strong> GentStationAI is designed around tenant isolation, role-based access,
                    and production separation between tenant operations and platform administration. This public landing page
                    intentionally does not expose logs, health, queue status, or internal debug information.
                </div>

                <div class="standalone-final-cta">
                    <p class="standalone-final-cta-copy">
                        Ready to enter the operational workspace? Open the application to start the boot sequence, validate runtime dependencies, and continue to the dedicated login page.
                    </p>
                    <a class="standalone-btn standalone-btn-primary" href="{_launch_href(launch_app='1', login_view='1')}">Launch Workspace</a>
                </div>
            </div>
        </div>
        """
    )
    st.markdown(
        public_site_html,
        unsafe_allow_html=True,
    )


def render_login_page() -> None:
    st.markdown(
        """
        <style>
            [data-testid="stHeader"] {
                background: transparent !important;
            }
            .login-stage {
                max-width: 640px;
                margin: 1rem auto 2rem auto;
            }
            .login-shell {
                border: 1px solid rgba(15, 23, 42, 0.08);
                border-radius: 24px;
                background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,248,251,0.96));
                box-shadow: 0 24px 50px rgba(15, 23, 42, 0.08);
                padding: 1.6rem;
            }
            .login-topline {
                font-size: 0.76rem;
                font-weight: 900;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #0b5ed7;
            }
            .login-title {
                margin: 0.55rem 0 0 0;
                font-size: 1.9rem;
                font-weight: 900;
                color: #0f172a;
            }
            .login-copy {
                margin: 0.75rem 0 0 0;
                font-size: 0.95rem;
                line-height: 1.65;
                color: #64748b;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="login-stage"><div class="login-shell">', unsafe_allow_html=True)
    top_col1, top_col2 = st.columns([0.22, 0.78], gap="small", vertical_alignment="center")
    with top_col1:
        if st.button("← Public Site", key="back_to_public_site", use_container_width=True):
            _clear_launch_params()
            st.rerun()
    with top_col2:
        st.markdown(
            """
            <div class="login-topline">Workspace Access</div>
            <h1 class="login-title">Secure application login</h1>
            <p class="login-copy">
                The application boot sequence has completed. Authorized tenant users can now sign in to access dashboards,
                reporting, subscription controls, and station operations.
            </p>
            """,
            unsafe_allow_html=True,
        )

    with st.form("login_form"):
        cred = st.text_input("Username or Email")
        pw = st.text_input("Password", type="password")
        ack = st.checkbox("I acknowledge the AI usage disclaimer")
        submitted = st.form_submit_button("Login to Workspace", use_container_width=True)
        if submitted:
            if not ack:
                st.error("You must acknowledge the disclaimer to log in.")
            else:
                ok, msg = login_user_streamlit(st, cred, pw)
                if ok:
                    try:
                        del st.query_params["login_view"]
                    except Exception:
                        pass
                    st.rerun()
                else:
                    st.error(msg)

    st.markdown(LOGIN_DISCLAIMER_HTML, unsafe_allow_html=True)
    if st.button("Forgot Password?", key="forgot_password_button", type="secondary", use_container_width=True):
        st.session_state["show_forgot_pw"] = True

    if st.session_state.get("show_forgot_pw"):
        with st.form("forgot_pw_form"):
            st.subheader("Get a Temporary Password")
            st.caption("Phase 0 uses a temporary-password email flow. Token-based reset links remain a production-release requirement.")
            email_to_reset = st.text_input("Enter your registered email address")
            if st.form_submit_button("Email Temporary Password", use_container_width=True):
                if email_to_reset:
                    with get_connection(platform_access=True) as platform_conn:
                        send_password_reset_email(platform_conn, email_to_reset)
                else:
                    st.error("Please enter an email address.")

    st.markdown("</div></div>", unsafe_allow_html=True)
