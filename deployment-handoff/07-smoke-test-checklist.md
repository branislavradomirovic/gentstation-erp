# 07. Smoke Test Checklist

## Goal

Validate that the first AWS deployment is usable and that critical dependencies are wired correctly.

## Infrastructure validation

- Confirm the ALB target group reports the web target as healthy.
- Confirm the web ECS task is running.
- Confirm the PostgreSQL instance is reachable from ECS tasks.
- Confirm the Redis instance is reachable from ECS tasks.
- Confirm CloudWatch logs are available for all running services.

## Web application validation

- Open the public application URL over HTTPS.
- Confirm the login screen renders successfully.
- Confirm there is no startup error shown in the UI.
- Confirm the application URL matches `APP_LOGIN_URL`.

## Database validation

- Confirm the web service completed schema initialization successfully.
- Confirm no startup loop is caused by schema initialization failure.
- Confirm the initial admin account can be used, if bootstrap credentials were provided for first login.

## Worker validation

- Confirm the AI worker task is running, if AI is enabled.
- Confirm the Telegram worker task is running, if Telegram is enabled.
- Confirm the report scheduler task is running.
- Confirm worker logs do not show repeated crash loops.

## Integration validation

### SMTP

- Trigger or simulate an email-related workflow if email is enabled.
- Confirm SMTP authentication and outbound mail flow work as expected.

### Telegram

- Confirm the Telegram worker starts without token errors.
- Send a basic message or test interaction if Telegram is enabled.

### Ollama

- Confirm the AI worker can reach `OLLAMA_BASE_URL`.
- Confirm the configured model endpoint is available if AI features are enabled.

## Functional spot checks inside the UI

- Confirm dashboard pages load.
- Confirm settings page loads.
- Confirm stations/regions pages load.
- Confirm map view loads without schema-readiness warnings.
- Confirm AI-related pages either work correctly or are explicitly considered out of scope for the release.

## Exit criteria

The deployment can be considered minimally successful when:

- the web service is healthy
- login page is reachable
- database connectivity is stable
- Redis connectivity is stable
- enabled worker services remain up
- enabled integrations are reachable
