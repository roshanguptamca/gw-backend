const { chromium } = require("playwright");
const fs = require("node:fs");

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const origin = new URL(input.target).origin;
const secrets = input.users.flatMap((user) => [user.username, user.password, user.subject]).filter(Boolean);

function sanitizeText(value) {
  let result = String(value ?? "");
  for (const secret of secrets) {
    if (secret) result = result.split(secret).join("[REDACTED]");
  }
  return result
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[REDACTED_EMAIL]")
    .replace(/\b(?:\+?\d[\d ().-]{7,}\d)\b/g, "[REDACTED_PHONE]")
    .slice(0, 4000);
}

async function withPage(browser, run) {
  const context = await browser.newContext({
    serviceWorkers: "block",
    viewport: { width: 1024, height: 768 },
  });
  const page = await context.newPage();
  await page.route("**/*", async (route) => {
    let requestOrigin;
    try {
      requestOrigin = new URL(route.request().url()).origin;
    } catch {
      await route.abort();
      return;
    }
    if (requestOrigin !== origin) {
      await route.abort();
      return;
    }
    await route.continue();
  });
  try {
    return await run(page, context);
  } finally {
    await context.close();
  }
}

async function login(page, user, config) {
  await page.goto(new URL(config.path, origin).href, { waitUntil: "domcontentloaded" });
  await page.locator(config.username_selector).fill(user.username);
  await page.locator(config.password_selector).fill(user.password);
  await page.locator(config.submit_selector).click();
  await page.waitForURL((url) => url.origin === origin, { timeout: input.step_timeout_ms });
}

async function safeScreenshot(page) {
  await page.addStyleTag({
    content: `
      input, textarea, [data-securewise-sensitive], [data-personal-data] {
        filter: blur(12px) !important;
      }
    `,
  });
  await page.evaluate((values) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      let text = node.nodeValue || "";
      for (const value of values) {
        if (value) text = text.split(value).join("[REDACTED]");
      }
      text = text
        .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[REDACTED_EMAIL]")
        .replace(/\b(?:\+?\d[\d ().-]{7,}\d)\b/g, "[REDACTED_PHONE]");
      node.nodeValue = text;
    }
  }, secrets);
  return (await page.screenshot({ type: "jpeg", quality: 40, fullPage: false })).toString("base64");
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  const config = input.browser_config;
  const usersByRole = (role) => input.users.filter((user) => user.role === role);

  try {
    for (const [journeyIndex, journey] of input.journeys.entries()) {
      if (journey.key === "protected-page") {
        const user = usersByRole(journey.role)[0];
        if (!user) {
          results.push({ key: journey.key, status: "not_executed", reason: "required_test_identity_missing" });
          continue;
        }
        results.push(await withPage(browser, async (page, context) => {
          await login(page, user, config);
          await page.goto(new URL(journey.path, origin).href, { waitUntil: "domcontentloaded" });
          const allowed = await page.locator(journey.protected_selector).count() > 0;
          const screenshot = await safeScreenshot(page);
          return {
            key: journey.key,
            status: allowed ? "passed" : "inconclusive",
            expected: "An authenticated user can access the protected page.",
            actual: allowed ? "The protected page marker was visible." : "The protected page marker was not visible.",
            screenshot,
            trace: [{ step: "login", result: "completed" }, { step: "protected_page", result: allowed ? "visible" : "not_visible" }],
          };
        }));
      } else if (journey.key === "session-cookie") {
        const user = usersByRole(journey.role)[0];
        if (!user) {
          results.push({ key: journey.key, status: "not_executed", reason: "required_test_identity_missing" });
          continue;
        }
        results.push(await withPage(browser, async (page, context) => {
          await login(page, user, config);
          const cookies = await context.cookies(origin);
          const cookie = cookies.find((item) => item.name === config.session_cookie_name);
          const safeFlags = cookie ? {
            http_only: cookie.httpOnly,
            same_site: cookie.sameSite,
            secure: cookie.secure,
          } : null;
          const secureFlags = safeFlags?.http_only
            && ["Lax", "Strict"].includes(safeFlags.same_site);
          const screenshot = await safeScreenshot(page);
          return {
            key: journey.key,
            status: secureFlags ? "passed" : (cookie ? "confirmed_vulnerability" : "inconclusive"),
            expected: "The session cookie is HttpOnly and uses SameSite=Lax or Strict.",
            actual: cookie ? "Session cookie flags were inspected." : "The configured session cookie was not set.",
            screenshot,
            trace: [{ step: "inspect_session_cookie_flags", result: safeFlags }],
          };
        }));
      } else if (journey.key === "cross-user-resource") {
        const owners = usersByRole(journey.owner_role);
        const requesters = usersByRole(journey.requester_role);
        if (!owners[0] || !requesters.find((user) => user.subject !== owners[0].subject)) {
          results.push({ key: journey.key, status: "not_executed", reason: "two_distinct_test_identities_required" });
          continue;
        }
        const owner = owners[0];
        const requester = requesters.find((user) => user.subject !== owner.subject);
        results.push(await withPage(browser, async (page) => {
          await login(page, requester, config);
          const path = journey.path.replace("{owner_subject}", encodeURIComponent(owner.subject));
          await page.goto(new URL(path, origin).href, { waitUntil: "domcontentloaded" });
          const records = page.locator(journey.resource_selector);
          let exposed = false;
          for (let index = 0; index < await records.count(); index += 1) {
            const record = records.nth(index);
            const recordOwner = await record.getAttribute(journey.owner_attribute);
            if (recordOwner === owner.subject) exposed = true;
          }
          const screenshot = await safeScreenshot(page);
          return {
            key: journey.key,
            status: exposed ? "confirmed_vulnerability" : "passed",
            expected: "A different authenticated user cannot view another user's protected resource.",
            actual: exposed ? "A protected resource owned by another test identity was rendered." : "No protected resource belonging to the other identity was rendered.",
            exposed,
            screenshot,
            trace: [{ step: "login_as_requester", result: "completed" }, { step: "open_other_user_resource", result: exposed ? "protected_resource_visible" : "no_protected_resource_visible" }],
          };
        }));
      } else if (journey.key === "role-boundary") {
        const lowPrivilegeUser = input.users.find((user) => user.role !== journey.required_role);
        const authorizedUser = usersByRole(journey.required_role)[0];
        if (!lowPrivilegeUser || !authorizedUser) {
          results.push({ key: journey.key, status: "not_executed", reason: "authorized_and_lower_privileged_identities_required" });
          continue;
        }
        results.push(await withPage(browser, async (page) => {
          await login(page, lowPrivilegeUser, config);
          await page.goto(new URL(journey.path, origin).href, { waitUntil: "domcontentloaded" });
          const exposed = await page.locator(journey.protected_selector).count() > 0;
          const denied = await page.locator(journey.denied_selector).count() > 0;
          const screenshot = await safeScreenshot(page);
          return {
            key: journey.key,
            status: exposed ? "confirmed_vulnerability" : (denied ? "passed" : "inconclusive"),
            expected: `Only the ${journey.required_role} role can view the protected resource.`,
            actual: exposed ? "A lower-privileged identity rendered the protected resource marker." : (denied ? "The explicit access-denied marker was visible and protected content was absent." : "Neither protected content nor an explicit access-denied marker was observed."),
            exposed,
            screenshot,
            trace: [{ step: "login_as_lower_privileged_user", result: "completed" }, { step: "open_role_protected_page", result: exposed ? "protected_marker_visible" : "protected_marker_not_visible" }],
          };
        }));
        results.push(await withPage(browser, async (page) => {
          await login(page, authorizedUser, config);
          await page.goto(new URL(journey.path, origin).href, { waitUntil: "domcontentloaded" });
          const allowed = await page.locator(journey.protected_selector).count() > 0;
          const screenshot = await safeScreenshot(page);
          return {
            key: `${journey.key}-authorized`,
            status: allowed ? "passed" : "inconclusive",
            expected: `An identity with the ${journey.required_role} role can view the protected resource.`,
            actual: allowed ? "The authorized protected resource marker was visible." : "The authorized protected resource marker was not visible.",
            screenshot,
            trace: [{ step: "login_as_authorized_user", result: "completed" }, { step: "open_role_protected_page", result: allowed ? "protected_marker_visible" : "protected_marker_not_visible" }],
          };
        }));
      } else if (journey.key === "logout" || journey.key === "session-expiration") {
        const user = usersByRole(journey.role)[0];
        if (!user) {
          results.push({ key: journey.key, status: "not_executed", reason: "required_test_identity_missing" });
          continue;
        }
        results.push(await withPage(browser, async (page, context) => {
          await login(page, user, config);
          await page.goto(new URL(journey.protected_path, origin).href, { waitUntil: "domcontentloaded" });
          const before = await page.locator(journey.protected_selector).count() > 0;
          if (journey.key === "logout") {
            await page.locator(journey.logout_selector).click();
          } else {
            await page.evaluate(async (path) => {
              const response = await fetch(path, { method: "POST", credentials: "same-origin" });
              if (!response.ok) throw new Error("The fixture did not expire the synthetic session.");
            }, journey.expire_path);
          }
          await page.goto(new URL(journey.protected_path, origin).href, { waitUntil: "domcontentloaded" });
          const after = await page.locator(journey.protected_selector).count() > 0;
          const loginFormVisible = await page.locator(config.username_selector).count() > 0;
          const confirmed = before && after;
          const screenshot = await safeScreenshot(page);
          return {
            key: journey.key,
            status: confirmed ? "confirmed_vulnerability" : (before && !after && loginFormVisible ? "passed" : "inconclusive"),
            expected: journey.key === "logout" ? "Logout invalidates the authenticated session." : "An expired server-side session cannot access the protected page.",
            actual: confirmed ? "Protected page content remained visible after session invalidation." : (!after && loginFormVisible ? "The protected page required authentication." : "The protected page behavior was inconclusive."),
            exposed: confirmed,
            screenshot,
            trace: [{ step: "login", result: before ? "protected_content_visible" : "protected_content_missing" }, { step: journey.key, result: journey.key === "logout" ? "logout_clicked" : "session_cookies_cleared" }, { step: "reopen_protected_page", result: after ? "protected_content_visible" : "protected_content_not_visible" }],
          };
        }));
      }
      process.stderr.write(`${JSON.stringify({ progress: Math.round(((journeyIndex + 1) / input.journeys.length) * 100) })}\n`);
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify({ results }));
}

main().catch(() => {
  process.stdout.write(JSON.stringify({ error: "Playwright browser execution failed." }));
  process.exitCode = 1;
});
