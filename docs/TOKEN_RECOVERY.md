# CPToken Recovery

## Summary

Sometimes the integration stops responding. Entities show old values, and commands have no effect. A restart of Home Assistant (HA) fixes the problem for some time.

The cause is in the CPToken handling in `panasonic_iot_tw_api/core.py`. Two defects can stop all API calls:

- After 4 failed logins, the client never tries to log in again.
- When the server rejects the CPToken with a JSON reply, the client does not detect the rejection. It continues to send the dead token.

The debug log also contained the Panasonic password and the full CPToken.

This document describes the defects, compares the code with the osk2 HACS integration, and describes the fix.

The defects are present in commit `002c378` and earlier.

## Symptom

- Entities keep their last values and do not update.
- Commands from HA do not change the device.
- The coordinator reports success, so entities do not show "unavailable".
- A restart of HA usually fixes the problem.

## How the Client Uses the CPToken

1. `get_access_token()` sends the user name and password to `/api/Userlogin1`.
2. The server returns a `CPToken`, a `RefreshToken`, and an `ExpireTime`.
3. The client writes the reply to `/tmp/cptoken.json`.
4. Each API request sends the `CPToken` in a header.
5. Before each request, `check_access_token()` logs in again in these conditions:
   - The token is marked invalid.
   - `ExpireTime` is less than 60 seconds away.
   - The last call was more than 20 minutes ago.
6. At startup, the client loads the token from `/tmp/cptoken.json` if the file exists.

The client does not use the `/api/RefreshToken1` endpoint. It always logs in again with the user name and password.

## Root Causes

### 1. Permanent Login Lockout

`check_access_token()` returned `False` when `login_retries > 3`. Only a successful login reset `login_retries`. After the fourth failed login, the client made no more login attempts. Thus, no login could succeed and reset the counter.

Each `device_status()` call and each `get_power_log()` call starts its own login attempt. With two appliances, one poll makes about four login attempts. Each attempt has one try and a 20-second timeout.

Result: one slow or failed Panasonic login at token renewal time can stop the integration in one poll. Only a restart of HA clears the counter.

### 2. Rejected Token Not Detected

On HTTP 417, `fetch()` returned the JSON body to the caller. The client marked the token invalid only when the body was not JSON.

The server can send JSON for a token error. The osk2 integration defines these messages:

- `此CPToken已經逾時` (this CPToken has timed out)
- `無法依據您的CPToken,auth取得相關資料` (cannot get data for your CPToken and auth)

`device_status()` then tried again three times with the same token. The token stayed "valid" until the local `ExpireTime` check started a login.

### 3. Dead Token Reused After Restart

At startup, the client loaded `/tmp/cptoken.json` and marked the token valid. It did not check the token with the server. Because of defect 2, the client did not delete the file when the server rejected the token. Thus, device discovery could fail again after a restart.

### 4. Failures Hidden From HA

`PanasonicAppliance.async_update()` logged an error and returned `None` on failure. The coordinator always reported success. Thus, entities showed old values and did not show "unavailable".

### 5. Command Crash Without a Response

`device_control()` called `.get()` on the result of `fetch()`. When `fetch()` returned `None`, the command raised `AttributeError`.

### 6. No Login Lock

A command and a poll could both start a login at the same time. If a new login makes the previous token invalid, a request in progress fails. This server behavior is not confirmed.

### 7. Credentials in the Debug Log

`fetch()` wrote all request headers and the request body to the debug log. For the login request, the body contains `MemId` (the user name) and `PW` (the password) in plain text. Every other request wrote the full `CPToken` and the device `auth` value. `async_setup_entry()` also wrote the user name.

Result: when the log level is `debug`, the HA log contains the Panasonic password and a token that stays valid for 90 days.

### 8. Immediate Retry After a Rate Limit

When the server replied HTTP 429 (too many requests), `fetch()` logged an error and sent the request again at once. The callers also tried again: `device_status()` up to 3 more times, and the power-log and discovery calls up to 3 times in `fetch()`. Thus, one 429 reply could cause a burst of 4 or more requests while the server limited the account.

For 6 appliances, one poll sends 12 status requests and 6 power-log requests in about 5 seconds. On 2026-10-24, the live system got a 429 reply at 23:22:05. This was the first scheduled poll after two restarts within 20 minutes.

### Possible Cause: Time Zone Offset

`ExpireTime` has no time zone. The client compares it with `datetime.datetime.now()`, which uses the time zone of the HA host. If the server sends Taiwan time and the host uses UTC, the client thinks that the token is valid for 8 hours after it expires. With defect 2, this gives up to 8 hours with no response.

On the live system, this cause does not apply. On 2026-10-24, HA logged in at 22:57:32 host time. The `ExpireTime` was 2027-01-22 22:57:32, exactly 90 days later. Thus, the server and the host use the same time zone.

On a different host, compare `ExpireTime` in `/tmp/cptoken.json` with the output of `date` in the HA container.

## Comparison With osk2/panasonic_smart_app

The HACS integration [osk2/panasonic_smart_app](https://github.com/osk2/panasonic_smart_app) is the version that most users install. Its token code has not changed since 2021.

The original [PhantasWeng/panasonic_smart_app](https://github.com/PhantasWeng/panasonic_smart_app) is a 2021 prototype for air conditioners only. Its README recommends osk2. It logs in once and logs in again after any exception.

| Item | osk2 | This integration before the fix |
| --- | --- | --- |
| Token storage | Memory only | `/tmp/cptoken.json`, loaded at startup without a check |
| Expiry detection | The server rejects the token | Local `ExpireTime` compared with `datetime.now()` |
| 417 with a JSON token message | Log in again and try the request once more | Return the body as data. The token stays valid. |
| 417 without a JSON body | Log in again and try the request once more | Mark the token invalid and delete the file |
| 417 with a command error or device offline | Log in again for a command error (osk2 issue #179) | No login |
| Login failure | `UpdateFailed`. The next poll tries again. | Permanent stop after 4 failures |
| Concurrent logins | No lock | No lock |
| `RefreshToken1` | Used only after the message `無效RefreshToken` (invalid refresh token). In practice, osk2 always logs in again. | Not used |
| Request spacing | 2 seconds between requests | None |
| HA state on failure | Entities become unavailable | Entities keep old values |

The osk2 design keeps no token state between polls. Thus, each poll can recover. This integration trusted its local expiry calculation and its cache file, and it could stay in a failed state.

## Fix

The fix uses the osk2 recovery method. It keeps the existing filter for command errors.

Changes in [core.py](../custom_components/panasonic_smart_app/panasonic_iot_tw_api/core.py):

- **Remove the lockout.** After a failed login, `_login_with_backoff()` skips new login attempts for `LOGIN_RETRY_BACKOFF` (60 seconds). Each 5-minute poll can try to log in again. During an outage, each poll makes one login attempt.
- **Detect a rejected token.** `fetch()` treats a 417 reply as a token rejection in these conditions:
  - The request sent a `CPToken`, and the body is not JSON.
  - The request sent a `CPToken`, and `StateMsg` is in `TOKEN_REJECTED_MESSAGES`.
- **Recover from a rejected token.** `_renew_rejected_token()` deletes `/tmp/cptoken.json` and logs in. Then `fetch()` tries the request once more with the new token.
- **Prevent a login loop.** If the server rejects a token that is less than 60 seconds old, the client does not log in again. This case can occur when a device `auth` value is not valid.
- **Keep command errors separate.** A 417 reply with `COMMAND_FAIL` or a device offline message does not start a login.
- **Add a login lock.** `login_lock` covers the token check and the login. When many requests fail at the same time, only one login occurs.
- **Check the login reply.** A login reply without `CPToken` counts as a failure.
- **Make commands safe.** `device_control()` returns `False` when `fetch()` returns no response.
- **Stop after a rate limit.** On HTTP 429, `fetch()` sends no retry. It sends no request to the server for `RATE_LIMIT_COOLDOWN` (60 seconds). Requests in this period return no response at once.
- **Space requests.** Each request starts at least `REQUEST_SPACING` (1 second) after the start of the previous request. A lock keeps concurrent requests in a queue. Thus, one poll of 18 requests takes about 20 seconds. On 2026-10-24, the first live poll with spacing took 23 seconds. The osk2 integration uses 2 seconds.
- **Remove credentials from logs.** `_redact()` masks credentials before `fetch()` writes headers, request bodies, and server replies to the log:
  - `PW`, `MemId`, `RefreshToken`, and `auth` show as `***`.
  - `CPToken` shows as `***` and its last 4 characters. Thus, you can see when the token changes.
  - `async_setup_entry()` does not write the user name.

Changes in the appliance and the coordinator:

- `PanasonicAppliance.async_update()` returns `True` on success and `False` on failure.
- `panasonic_iot_tw_api.async_update()` returns one result for each appliance.
- The coordinator calls `_raise_if_all_failed()` in [\_\_init\_\_.py](../custom_components/panasonic_smart_app/__init__.py). When all appliances fail, it raises `UpdateFailed`, and entities show "unavailable". When only some appliances fail, the coordinator reports success.

Behavior change: when all appliances fail, the energy sensors also show "unavailable" for that poll. The coordinator skips the power-log update in that case.

## Verification

[scripts/test_token_recovery.py](../scripts/test_token_recovery.py) tests the client with a fake HTTP session. It needs no extra packages.

```bash
python3 scripts/test_token_recovery.py
```

| Scenario | Fixed code | Code at `002c378` |
| --- | --- | --- |
| 417 with a token-expired message: one login, then the request succeeds | Pass | Fail |
| 417 without a JSON body: one login, then the request succeeds | Pass | Pass |
| A login succeeds after 5 failed logins | Pass | Fail |
| One login attempt during the backoff period | Pass | Fail (4 attempts) |
| Two requests rejected at the same time: one login | Pass | Fail |
| Rejection of a fresh token: no second login | Pass | Fail (no login at all) |
| 417 with `COMMAND_FAIL`: no login | Pass | Pass |
| `device_control()` without a response returns `False` | Pass | Crash (`AttributeError`) |
| The debug log of a login and a status request contains no credentials | Pass | Not run (added later) |
| HTTP 429: no retry, and no request during the cooldown | Pass | Not run (added later) |
| Concurrent requests start at least the spacing interval apart | Pass | Not run (added later) |

To check the fix in HA:

1. Set the log level of `custom_components.panasonic_smart_app` to `debug`.
2. Look for the message `rejected the CPToken`.
3. Make sure that a successful request follows the message.

## Open Items

- The fix runs on the live system since 2026-10-24. Normal polls work. The recovery path is not yet seen live, because it runs only when the server rejects a token.
- The token lifetime is 90 days. The live login on 2026-10-24 confirms this value.
- The server messages for a rejected token come from the osk2 constants. The server can use other messages.
- HA logs written at the `debug` level before the log fix can contain the Panasonic password. Delete these logs, or change the password.
- `/tmp/cptoken.json` holds the token as plain text. All accounts on the host share this file.
