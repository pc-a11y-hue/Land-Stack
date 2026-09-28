# Put the working app online (free, no command line)

Result: a public address like `https://land-stack-xxxx.onrender.com` that judges can open on any phone,
log in with the demo accounts, and even "Install" as an app. You need a GitHub account and a Render account (both free).
Website screens change now and then — if a button is named slightly differently, pick the closest one.

## Before you start
1. Extract the zip. If you ever ran the app inside this folder, **delete the folder `backend\data`** (it holds your local test database).
2. Open the extracted `land-stack-prototype` folder. Inside you should see: `backend`, `frontend`, `tests`, `tools`, `docs`, `README.md`, **`render.yaml`**.

## Part 1 — Upload the code to GitHub
1. Go to https://github.com and sign in (or sign up).
2. Click **+** (top right) → **New repository**. Name it `land-stack`, keep it **Public**, click **Create repository**.
3. On the next page click the link **uploading an existing file**.
4. In File Explorer, open `land-stack-prototype`, press **Ctrl + A** to select everything **inside** it, and drag it all into the browser page.
   (Drag the *contents*, not the outer folder — `render.yaml` must end up at the top level of the repository.)
5. Wait until every file shows as uploaded, then click **Commit changes**.

## Part 2 — Start it on Render
1. Go to https://render.com → **Get Started** → sign in with **GitHub** and allow access to your `land-stack` repository.
2. Click **New +** → **Blueprint**, choose the `land-stack` repository, click **Connect**.
3. Render reads `render.yaml` and shows one service called `land-stack`. Click **Apply** (or **Deploy**).
4. Wait for the build to finish and the status to turn **Live**. The first start also creates the database, so allow several minutes.
5. Click the web address shown near the top of the service page. Add `/citizen` or `/officer` to open a portal.

## Part 3 — Try it and install it on a phone
* Log in with the **Try a demo account** picker, or `reg_coimbatore` / `regcoimbatore123` on `/officer`.
* On a phone, open the address in Chrome → menu (⋮) → **Install app** / **Add to Home screen**. It opens full-screen like an app.

## Things to know before judges use it
* **It falls asleep** after some idle time on the free plan. The first visit after a break can take about a minute — open it yourself a few minutes before you present.
* **Data resets** whenever it restarts (the free plan does not keep files). That is fine for a demo: it re-creates the same 92 sample plots.
* **Demo accounts are public on purpose** (`LANDSTACK_DEMO_MODE=1`), because the data is synthetic. Never put real people's data into this deployment.
* Free-plan limits and pricing are set by the host and can change — check Render's current terms.
* If the build fails, open the **Logs** tab, copy the last 30 lines and send them to me.

## Why "1 worker"?
`render.yaml` starts the app with `--workers 1 --threads 8`. The prototype keeps its working data in memory and uses a
single-writer SQLite file, so extra worker *processes* would each see different data. The Technical Document (§11) explains
the production design (PostgreSQL + Redis) that removes this limit.
