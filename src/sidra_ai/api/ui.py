"""One HTML page for asking SIDRA a question from a browser.

Why a hand-written page and not a framework: this service binds to loopback
and enables no CORS, so anything the page fetches from another host simply
does not arrive. A build step or a CDN script tag would make the page load
and the button do nothing, which is worse than no page at all. Everything
here - markup, style, script - is inline and self-contained.

What it deliberately does not do:

* No credential storage. The token box is a plain field whose value goes
  into one ``Authorization`` header and nowhere else: not ``localStorage``,
  not the URL, not the page title.
* No new endpoint. The page posts to ``/v1/chat`` like any other client, so
  the answer it shows went through the same guards as ``sidra-ask``.
* No content rendered as markup. Answers and citation text are inserted as
  text nodes, because a retrieved document is DATA and must never become
  markup in the operator's browser.
* No artifact opened in this origin. A generated file is downloaded through
  ``fetch`` and handed to the browser as a blob; it is never put in an
  ``iframe`` or a same-origin tab, where its markup would run next to the
  field the operator types their token into.
"""

from __future__ import annotations

#: The page is served under the same auth dependency as the private API, so
#: with a token configured a browser cannot load it by navigation alone. The
#: field below still exists because that is the posture the page cannot fix
#: on its own, and an operator reaching this page through a client that can
#: set headers still needs the header on the ``/v1/chat`` call it makes.
ASK_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>SIDRA AI</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: system-ui, sans-serif;
    max-width: 46rem; margin: 0 auto; padding: 1.5rem; line-height: 1.6;
  }
  h1 { font-size: 1.25rem; margin: 0 0 .25rem; }
  p.sub { margin: 0 0 1.5rem; opacity: .7; font-size: .875rem; }
  label { display: block; font-size: .8125rem; opacity: .8; margin-bottom: .25rem; }
  textarea, input {
    width: 100%; box-sizing: border-box; font: inherit;
    padding: .5rem; border: 1px solid currentColor; border-radius: .25rem;
    background: transparent; color: inherit;
  }
  textarea { min-height: 5rem; resize: vertical; }
  .row { margin-bottom: 1rem; }
  button { font: inherit; padding: .5rem 1.25rem; border-radius: .25rem; cursor: pointer; }
  button[disabled] { opacity: .5; cursor: progress; }
  /* On a phone the 更新 and per-file 開く buttons came out 41-42px tall,
     under the 48dp minimum a touch target needs - this is the page an author
     opens on their phone to grab a generated file (C-1224). No button sets a
     height, so one rule scoped to a coarse pointer lifts them all; the desktop
     keeps its compact controls. Same fix the game shell already carries. */
  @media (pointer: coarse) { button { min-height: 48px; } }
  /* overflow-wrap on the answer and status for the same reason .path has
     it: citation labels and error text carry long unbroken tokens, and on
     a phone one such token widens the document past the viewport - the
     browser then shrinks every glyph on the page to fit (C-1214). */
  #answer { white-space: pre-wrap; overflow-wrap: anywhere; margin: 1.5rem 0 0; }
  #status { margin: 1rem 0 0; font-size: .875rem; opacity: .8; overflow-wrap: anywhere; }
  ol { padding-left: 1.25rem; }
  li { margin-bottom: .5rem; font-size: .875rem; }
  .path { font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
  .note { font-size: .8125rem; opacity: .7; }
</style>
</head>
<body>
<h1>SIDRA AI</h1>
<p class="sub">索引済みリポジトリについて質問できます。回答は取得した文書に
基づき、どの記述がどこから来たかを出典で示します。</p>
<p class="sub">作るときも同じ欄です。「釣りゲームを作って」「デッキを作って」の
ように書けば、質問ではなく制作として扱われ、できたファイルが下に並びます。</p>

<form id="ask">
  <div class="row">
    <label for="q">質問</label>
    <textarea id="q" name="q" required autofocus></textarea>
  </div>
  <div class="row">
    <label for="token">アクセストークン（設定していなければ空欄のまま）</label>
    <input id="token" name="token" type="password" autocomplete="off">
  </div>
  <button type="submit" id="send">送信</button>
</form>

<p id="status"></p>
<p id="answer"></p>
<div id="sources"></div>

<section id="artifacts">
  <p class="note">生成ファイル
    <button type="button" id="refresh">更新</button>
  </p>
  <ol id="artifact-list"></ol>
  <p class="note" id="artifact-status"></p>
</section>

<section id="projects">
  <p class="note">プロジェクト（ひとまとまりの制作物）</p>
  <ol id="project-list"></ol>
  <p class="note" id="project-status"></p>
</section>

<script>
(function () {
  var form = document.getElementById("ask");
  var send = document.getElementById("send");
  var statusLine = document.getElementById("status");
  var answer = document.getElementById("answer");
  var sources = document.getElementById("sources");

  // Status codes an operator can act on, said in their language (C-1211).
  // The response BODY stays hidden on purpose - a detail the API kept
  // private must stay private - but the class of failure is not a secret,
  // and "HTTP 422" alone tells an operator nothing about what to do next.
  function explain(status) {
    var why = "";
    if (status === 401 || status === 403) { why = "\u30a2\u30af\u30bb\u30b9\u30c8\u30fc\u30af\u30f3\u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044"; }
    else if (status === 404) { why = "\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002\u4e00\u89a7\u3092\u66f4\u65b0\u3057\u3066\u304f\u3060\u3055\u3044\uff08\u6d88\u3048\u305f\u304b\u540d\u524d\u304c\u5909\u308f\u3063\u305f\u53ef\u80fd\u6027\uff09"; }
    else if (status === 413 || status === 422) { why = "\u5165\u529b\u304c\u9577\u3059\u304e\u308b\u304b\u5f62\u5f0f\u304c\u4e0d\u6b63\u3067\u3059\u3002\u77ed\u304f\u3057\u3066\u518d\u9001\u3057\u3066\u304f\u3060\u3055\u3044"; }
    else if (status === 429) { why = "\u6df7\u307f\u5408\u3063\u3066\u3044\u307e\u3059\u3002\u5c11\u3057\u5f85\u3063\u3066\u304b\u3089\u3082\u3046\u4e00\u5ea6\u304a\u8a66\u3057\u304f\u3060\u3055\u3044"; }
    else if (status >= 500) { why = "\u30b5\u30fc\u30d0\u5074\u3067\u554f\u984c\u304c\u8d77\u304d\u307e\u3057\u305f\u3002\u6642\u9593\u3092\u304a\u3044\u3066\u518d\u8a66\u884c\u3057\u3066\u304f\u3060\u3055\u3044"; }
    return why ? why + "\uff08HTTP " + status + "\uff09" : "HTTP " + status;
  }

  // A fetch that never gets a response (server down, offline, connection
  // dropped) rejects with a TypeError whose message is an English browser
  // string - "Failed to fetch" / "Load failed" - which is meaningless in a
  // Japanese UI and says nothing about what to do (C-1218). Our own
  // HTTP-status errors are thrown as Error(explain(...)) and are already
  // Japanese, so only the network-level rejection needs translating.
  function reason(error) {
    if (error instanceof TypeError) {
      return "\u30b5\u30fc\u30d0\u30fc\u306b\u63a5\u7d9a\u3067\u304d\u307e\u305b\u3093\u3002\u30ed\u30fc\u30ab\u30eb\u306e sidra-api \u304c\u8d77\u52d5\u3057\u3066\u3044\u308b\u304b\u3001\u63a5\u7d9a\u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044";
    }
    return error.message;
  }

  function clear(node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  function render(result) {
    // Text nodes only. Retrieved content is DATA, so it is never parsed as
    // markup here, whatever a document happens to contain.
    answer.textContent = result.answer || "";
    if (result.refused) {
      // The API reason is the gate's English audit text; a Japanese user needs
      // Japanese and a next step, not the audit trail (C-1238). Chosen by the
      // machine-readable security.decision: a gate refusal (quarantine/block)
      // asks for a rephrase, any other refusal asks to retry. The raw English
      // reason is left in the API response for consumers, not shown here.
      var decision = (result.security || {}).decision;
      var refusalMsg = (decision === "quarantine" || decision === "block")
        ? "\u62d2\u5426\u3055\u308c\u307e\u3057\u305f\u3002\u5165\u529b\u304c\u5b89\u5168\u6027\u30c1\u30a7\u30c3\u30af\u306b\u304b\u304b\u308a\u307e\u3057\u305f\u3002\u6307\u793a\u306e\u4e0a\u66f8\u304d\u3084\u79d8\u5bc6\u60c5\u5831\u3092\u542b\u3080\u8868\u73fe\u3092\u907f\u3051\u3001\u8a00\u3044\u63db\u3048\u3066\u3082\u3046\u4e00\u5ea6\u304a\u8a66\u3057\u304f\u3060\u3055\u3044\u3002"
        : "\u62d2\u5426\u3055\u308c\u307e\u3057\u305f\u3002\u56de\u7b54\u3092\u51fa\u305b\u307e\u305b\u3093\u3067\u3057\u305f\u3002\u5c11\u3057\u6642\u9593\u3092\u304a\u3044\u3066\u3001\u3082\u3046\u4e00\u5ea6\u304a\u8a66\u3057\u304f\u3060\u3055\u3044\u3002";
      statusLine.textContent = refusalMsg;
    }
    clear(sources);
    var citations = result.citations || [];
    if (!citations.length) { return; }
    var heading = document.createElement("p");
    heading.className = "note";
    heading.textContent = "\u51fa\u5178";
    sources.appendChild(heading);
    var list = document.createElement("ol");
    citations.forEach(function (c) {
      var item = document.createElement("li");
      var label = document.createElement("strong");
      label.textContent = (c.label || "") + " ";
      item.appendChild(label);
      var where = document.createElement("span");
      where.className = "path";
      where.textContent = (c.repository || "") + " " + (c.path || "");
      item.appendChild(where);
      if (c.redacted) {
        var flag = document.createElement("span");
        flag.className = "note";
        flag.textContent = " \uff08\u4f0f\u305b\u5b57\u3042\u308a\uff09";
        item.appendChild(flag);
      }
      // A whole-excerpt block at answer time (C-1236): the service marks it
      // excerpt_withheld so this can be told apart from an ordinary citation,
      // which the page dropped. Shown beside the redacted flag, not instead of
      // it - a source can be both redacted at ingestion and withheld here.
      if (c.excerpt_withheld) {
        var held = document.createElement("span");
        held.className = "note";
        held.textContent = " \uff08\u629c\u7c8b\u3092\u79d8\u533f\uff09";
        item.appendChild(held);
      }
      list.appendChild(item);
    });
    sources.appendChild(list);
  }

  var artifactList = document.getElementById("artifact-list");
  var artifactStatus = document.getElementById("artifact-status");
  // How many generated files the entry page lists at once (C-1252). The list is
  // newest-first, so this is the recent handful; the rest is reported as a count.
  var ARTIFACT_LIMIT = 20;

  function authHeaders() {
    var token = document.getElementById("token").value;
    return token ? { "Authorization": "Bearer " + token } : {};
  }

  function download(name) {
    // Fetched rather than linked: a plain <a href> cannot carry the bearer
    // token, and a blob is handed to the browser instead of being opened in
    // this origin.
    fetch("/v1/artifacts/" + encodeURIComponent(name), { headers: authHeaders() })
      .then(function (response) {
        if (!response.ok) { throw new Error(explain(response.status)); }
        return response.blob();
      }).then(function (blob) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = name;
        link.click();
        URL.revokeObjectURL(url);
      }).catch(function (error) {
        artifactStatus.textContent = "\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u306b\u5931\u6557: " + reason(error);
      });
  }

  function loadArtifacts() {
    fetch("/v1/artifacts", { headers: authHeaders() })
      .then(function (response) {
        if (!response.ok) { throw new Error(explain(response.status)); }
        return response.json();
      }).then(function (result) {
        clear(artifactList);
        var items = result.artifacts || [];
        // The list arrives newest-first. Every generation adds one, so an
        // uncapped list grew to hundreds of rows - on a phone the entry page
        // became a ~50,000px scroll that buried the projects section (C-1252).
        // Show a recent slice; the note reports the total so nothing is hidden
        // without saying so.
        var shown = items.slice(0, ARTIFACT_LIMIT);
        if (!items.length) {
          artifactStatus.textContent = "まだありません。";
        } else if (items.length > ARTIFACT_LIMIT) {
          artifactStatus.textContent =
            "新しい順に " + ARTIFACT_LIMIT + " 件を表示（全 " + items.length + " 件）。";
        } else {
          artifactStatus.textContent = "";
        }
        shown.forEach(function (a) {
          // Name, size and time. The server sends nothing else, and the page
          // asks for nothing else.
          var item = document.createElement("li");
          var open = document.createElement("button");
          open.type = "button";
          open.textContent = a.name;
          open.addEventListener("click", function () { download(a.name); });
          item.appendChild(open);
          var meta = document.createElement("span");
          meta.className = "note";
          meta.textContent = " " + a.bytes + " bytes / " + a.modified;
          item.appendChild(meta);
          artifactList.appendChild(item);
        });
      }).catch(function (error) {
        artifactStatus.textContent = "\u4e00\u89a7\u306e\u53d6\u5f97\u306b\u5931\u6557: " + reason(error);
      });
  }

  var projectList = document.getElementById("project-list");
  var projectStatus = document.getElementById("project-status");

  function downloadProjectFile(slug, name) {
    // Same blob route as single artifacts: the token travels in a header,
    // and the generated markup never opens in this origin.
    fetch("/v1/projects/" + encodeURIComponent(slug) + "/" + name.split("/").map(encodeURIComponent).join("/"),
      { headers: authHeaders() })
      .then(function (response) {
        if (!response.ok) { throw new Error(explain(response.status)); }
        return response.blob();
      }).then(function (blob) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = name.split("/").pop();
        link.click();
        URL.revokeObjectURL(url);
      }).catch(function (error) {
        projectStatus.textContent = "\u30c0\u30a6\u30f3\u30ed\u30fc\u30c9\u306b\u5931\u6557: " + reason(error);
      });
  }

  function loadProjects() {
    fetch("/v1/projects", { headers: authHeaders() })
      .then(function (response) {
        if (!response.ok) { throw new Error(explain(response.status)); }
        return response.json();
      }).then(function (result) {
        clear(projectList);
        var items = result.projects || [];
        projectStatus.textContent = items.length ? "" : "まだありません。";
        items.forEach(function (p) {
          // One entry per production. The slug and the file names are the
          // server's own metadata; production-log.md inside answers "when,
          // from what, with which parameters".
          var item = document.createElement("li");
          var name = document.createElement("span");
          name.className = "path";
          name.textContent = p.slug;
          item.appendChild(name);
          var meta = document.createElement("span");
          meta.className = "note";
          meta.textContent = " " + p.modified;
          item.appendChild(meta);
          var files = document.createElement("ol");
          (p.files || []).forEach(function (f) {
            var row = document.createElement("li");
            var open = document.createElement("button");
            open.type = "button";
            open.textContent = f.name;
            open.addEventListener("click", function () {
              downloadProjectFile(p.slug, f.name);
            });
            row.appendChild(open);
            var size = document.createElement("span");
            size.className = "note";
            size.textContent = " " + f.bytes + " bytes";
            row.appendChild(size);
            files.appendChild(row);
          });
          item.appendChild(files);
          projectList.appendChild(item);
        });
      }).catch(function (error) {
        projectStatus.textContent = "\u4e00\u89a7\u306e\u53d6\u5f97\u306b\u5931\u6557: " + reason(error);
      });
  }

  document.getElementById("refresh").addEventListener("click", function () {
    loadArtifacts();
    loadProjects();
  });

  // The conversation, page-lifetime only (C-1210). The server has carried
  // /v1/chat history since the envelope work, but this page never sent it,
  // so every browser follow-up ("それはなぜ？") retrieved nothing and got
  // the honest abstention. Kept in a variable, never in browser storage
  // (the posture is pinned by test), so closing the tab ends the
  // conversation - which is also the privacy this page promises.
  var turns = [];
  var MAX_TURNS = 8;

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var question = document.getElementById("q").value.trim();
    if (!question) { return; }
    var token = document.getElementById("token").value;

    send.disabled = true;
    statusLine.textContent = "\u554f\u3044\u5408\u308f\u305b\u4e2d\u2026";
    answer.textContent = "";
    clear(sources);

    var headers = { "Content-Type": "application/json" };
    if (token) { headers["Authorization"] = "Bearer " + token; }

    var payload = { message: question };
    if (turns.length) { payload.history = turns.slice(-MAX_TURNS); }

    fetch("/v1/chat", {
      method: "POST",
      headers: headers,
      body: JSON.stringify(payload)
    }).then(function (response) {
      if (!response.ok) {
        // Status only. The body of an error response is not shown, so a
        // detail the API chose to keep private stays private.
        throw new Error(explain(response.status));
      }
      return response.json();
    }).then(function (result) {
      statusLine.textContent = "";
      render(result);
      // Only a real exchange joins the conversation: a refusal or an empty
      // answer would replay noise into every later request.
      if (result && result.answer && !result.refused) {
        turns.push({ question: question, answer: result.answer });
        if (turns.length > MAX_TURNS) { turns = turns.slice(-MAX_TURNS); }
      }
      // A creation turn just wrote a file; the lists are stale the moment
      // the answer arrives.
      loadArtifacts();
      loadProjects();
    }).catch(function (error) {
      statusLine.textContent = "\u5931\u6557: " + reason(error);
    }).then(function () {
      send.disabled = false;
    });
  });

  loadArtifacts();
  loadProjects();
})();
</script>
</body>
</html>
"""
