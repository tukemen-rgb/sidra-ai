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
  #answer { white-space: pre-wrap; margin: 1.5rem 0 0; }
  #status { margin: 1rem 0 0; font-size: .875rem; opacity: .8; }
  ol { padding-left: 1.25rem; }
  li { margin-bottom: .5rem; font-size: .875rem; }
  .path { font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
  .note { font-size: .8125rem; opacity: .7; }
</style>
</head>
<body>
<h1>SIDRA AI</h1>
<p class="sub">Ask a question about the indexed repositories. Answers are
grounded in retrieved documents and cite where each claim came from.</p>

<form id="ask">
  <div class="row">
    <label for="q">Question</label>
    <textarea id="q" name="q" required autofocus></textarea>
  </div>
  <div class="row">
    <label for="token">API token (leave empty if none is configured)</label>
    <input id="token" name="token" type="password" autocomplete="off">
  </div>
  <button type="submit" id="send">Ask</button>
</form>

<p id="status"></p>
<p id="answer"></p>
<div id="sources"></div>

<script>
(function () {
  var form = document.getElementById("ask");
  var send = document.getElementById("send");
  var statusLine = document.getElementById("status");
  var answer = document.getElementById("answer");
  var sources = document.getElementById("sources");

  function clear(node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  function render(result) {
    // Text nodes only. Retrieved content is DATA, so it is never parsed as
    // markup here, whatever a document happens to contain.
    answer.textContent = result.answer || "";
    if (result.refused) {
      statusLine.textContent = "Refused" + (result.reason ? ": " + result.reason : "");
    }
    clear(sources);
    var citations = result.citations || [];
    if (!citations.length) { return; }
    var heading = document.createElement("p");
    heading.className = "note";
    heading.textContent = "Sources";
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
        flag.textContent = " (redacted)";
        item.appendChild(flag);
      }
      list.appendChild(item);
    });
    sources.appendChild(list);
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var question = document.getElementById("q").value.trim();
    if (!question) { return; }
    var token = document.getElementById("token").value;

    send.disabled = true;
    statusLine.textContent = "Asking\\u2026";
    answer.textContent = "";
    clear(sources);

    var headers = { "Content-Type": "application/json" };
    if (token) { headers["Authorization"] = "Bearer " + token; }

    fetch("/v1/chat", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ message: question })
    }).then(function (response) {
      if (!response.ok) {
        // Status only. The body of an error response is not shown, so a
        // detail the API chose to keep private stays private.
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    }).then(function (result) {
      statusLine.textContent = "";
      render(result);
    }).catch(function (error) {
      statusLine.textContent = "Failed: " + error.message;
    }).then(function () {
      send.disabled = false;
    });
  });
})();
</script>
</body>
</html>
"""
