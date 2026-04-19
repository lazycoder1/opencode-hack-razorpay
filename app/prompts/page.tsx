"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

type PromptLibraryItem = {
  id: string;
  name: string;
  slug: string;
  stage: string;
  description: string;
  content: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type PromptDraft = {
  id: string | null;
  name: string;
  stage: string;
  description: string;
  content: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const emptyDraft: PromptDraft = {
  id: null,
  name: "",
  stage: "microsite_generation",
  description: "",
  content: "",
};

function starterTemplate(stage: string) {
  if (stage === "mcp_research") {
    return [
      "You are gathering concise external context for a first-touch outbound microsite.",
      "Use the available MCP tools to research the prospect company and return only grounded, publicly supportable details.",
      "The prospect company is: {{company_name}}.",
    ].join(" ");
  }

  return [
    "You are generating a lightweight but visually distinctive outbound sales microsite.",
    "Keep the copy credible, discovery-oriented, and ready to be upgraded by a future research layer.",
    "The prospect company is: {{company_name}}.{{mcp_context_block}}",
  ].join(" ");
}

export default function PromptsPage() {
  const [prompts, setPrompts] = useState<PromptLibraryItem[]>([]);
  const [selectedPromptId, setSelectedPromptId] = useState("");
  const [draft, setDraft] = useState<PromptDraft>(emptyDraft);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadPrompts() {
    setLoading(true);

    try {
      const response = await fetch(`${apiBaseUrl}/api/prompts`);
      if (!response.ok) {
        throw new Error(`Unable to load prompt library: ${response.status}`);
      }

      const data: PromptLibraryItem[] = await response.json();
      setPrompts(data);

      const nextSelected = data.find((item) => item.id === selectedPromptId) ?? data[0] ?? null;
      if (!nextSelected) {
        setSelectedPromptId("");
        return;
      }

      setSelectedPromptId(nextSelected.id);
      setDraft({
        id: nextSelected.id,
        name: nextSelected.name,
        stage: nextSelected.stage,
        description: nextSelected.description,
        content: nextSelected.content,
      });
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to load prompt library");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPrompts();
  }, []);

  const selectedPrompt = useMemo(
    () => prompts.find((prompt) => prompt.id === selectedPromptId) ?? null,
    [prompts, selectedPromptId],
  );

  const groupedPrompts = useMemo(
    () => ({
      mcp_research: prompts.filter((prompt) => prompt.stage === "mcp_research"),
      microsite_generation: prompts.filter((prompt) => prompt.stage === "microsite_generation"),
    }),
    [prompts],
  );

  function selectPrompt(prompt: PromptLibraryItem) {
    setSelectedPromptId(prompt.id);
    setDraft({
      id: prompt.id,
      name: prompt.name,
      stage: prompt.stage,
      description: prompt.description,
      content: prompt.content,
    });
    setError("");
    setNotice("");
  }

  function startNewPrompt(stage: string) {
    setSelectedPromptId("");
    setDraft({ ...emptyDraft, stage, content: starterTemplate(stage) });
    setError("");
    setNotice("");
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");

    try {
      const response = await fetch(
        draft.id ? `${apiBaseUrl}/api/prompts/${draft.id}` : `${apiBaseUrl}/api/prompts`,
        {
          method: draft.id ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: draft.name,
            stage: draft.stage,
            description: draft.description,
            content: draft.content,
          }),
        },
      );

      if (!response.ok) {
        throw new Error(`Unable to save prompt: ${response.status}`);
      }

      const saved: PromptLibraryItem = await response.json();
      await loadPrompts();
      setSelectedPromptId(saved.id);
      setNotice(draft.id ? "Prompt updated." : "Prompt created.");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to save prompt");
    } finally {
      setSaving(false);
    }
  }

  async function handleActivate() {
    if (!draft.id) {
      setError("Save the prompt before activating it.");
      return;
    }

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const response = await fetch(`${apiBaseUrl}/api/prompts/${draft.id}/activate`, { method: "POST" });
      if (!response.ok) {
        throw new Error(`Unable to activate prompt: ${response.status}`);
      }

      await loadPrompts();
      setNotice("Prompt activated for this stage.");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to activate prompt");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!draft.id) {
      setDraft(emptyDraft);
      return;
    }

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const response = await fetch(`${apiBaseUrl}/api/prompts/${draft.id}`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error(`Unable to delete prompt: ${response.status}`);
      }

      await loadPrompts();
      setSelectedPromptId("");
      setDraft(emptyDraft);
      setNotice("Prompt deleted.");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to delete prompt");
    } finally {
      setSaving(false);
    }
  }

  function renderPromptList(stage: "mcp_research" | "microsite_generation", title: string) {
    const items = groupedPrompts[stage];

    return (
      <section className="promptGroup">
        <div className="groupHeader">
          <div>
            <p className="miniLabel">{stage === "mcp_research" ? "Research stage" : "Generation stage"}</p>
            <strong>{title}</strong>
          </div>
          <button className="buttonTertiary" onClick={() => startNewPrompt(stage)} type="button">
            New prompt
          </button>
        </div>

        {items.length === 0 ? (
          <div className="emptyPanel promptEmptyPanel">
            <p>No prompts for this stage yet.</p>
          </div>
        ) : (
          <div className="selectorList">
            {items.map((prompt) => (
              <button
                className={`selectorButton ${prompt.id === selectedPromptId ? "active" : ""}`}
                key={prompt.id}
                onClick={() => selectPrompt(prompt)}
                type="button"
              >
                <div className="selectorTop">
                  <span>{prompt.is_active ? "active" : "draft"}</span>
                  <strong>{new Date(prompt.updated_at).toLocaleDateString()}</strong>
                </div>
                <strong className="selectorTitle">{prompt.name}</strong>
                <p>{prompt.description || prompt.slug}</p>
              </button>
            ))}
          </div>
        )}
      </section>
    );
  }

  return (
    <main className="pageShell">
      <nav className="topbar">
        <div className="brand">
          <div className="brandIcon">PL</div>
          <div className="brandBlock">
            <strong className="brandTitle">Prompt Library</strong>
            <span className="brandCaption">Stage-aware prompt editing and activation</span>
          </div>
        </div>

        <div className="navCluster">
          <Link className="navLink" href="/">
            New batch
          </Link>
          <Link className="navLink" href="/sandbox">
            Open sandbox
          </Link>
        </div>
      </nav>

      <section className="pageIntro">
        <div>
          <p className="kicker">Prompt management</p>
          <h1 className="pageTitle">Store, activate, and iterate on prompts without touching code.</h1>
          <p className="sectionText">
            Keep one active prompt per stage, test alternates safely, and update generation behavior without
            editing backend source files.
          </p>
        </div>

        <div className="metricGrid metricGridThree compactMetrics">
          <article className="metricCard">
            <span>Total prompts</span>
            <strong>{prompts.length}</strong>
          </article>
          <article className="metricCard">
            <span>MCP research</span>
            <strong>{groupedPrompts.mcp_research.length}</strong>
          </article>
          <article className="metricCard">
            <span>Microsite generation</span>
            <strong>{groupedPrompts.microsite_generation.length}</strong>
          </article>
        </div>
      </section>

      {error ? <p className="errorText">{error}</p> : null}
      {notice ? <p className="noticeText">{notice}</p> : null}

      <section className="promptLibraryGrid">
        <aside className="panel selectorPanel">
          <div className="panelHeader compactHeader">
            <div>
              <p className="kicker">Prompt sets</p>
              <h2 className="sectionTitle">Stage-aware prompt inventory</h2>
            </div>
          </div>

          {loading ? (
            <div className="emptyPanel promptEmptyPanel">
              <p>Loading prompt library...</p>
            </div>
          ) : (
            <div className="promptGroups">
              {renderPromptList("mcp_research", "MCP research")}
              {renderPromptList("microsite_generation", "Microsite generation")}
            </div>
          )}
        </aside>

        <section className="panel detailPanel">
          <div className="previewHeader">
            <div>
              <p className="kicker">Editor</p>
              <h2 className="sectionTitle">{draft.id ? draft.name || "Unnamed prompt" : "Create a new prompt"}</h2>
            </div>
            <span className={`statusChip ${selectedPrompt?.is_active ? "statusReady" : "statusPending"}`}>
              {selectedPrompt?.is_active ? "Active" : draft.id ? "Inactive" : "New draft"}
            </span>
          </div>

          <form className="promptEditorForm" onSubmit={handleSave}>
            <div className="promptEditorMeta">
              <label className="fieldGroup">
                <div className="fieldLabel">
                  <strong>Name</strong>
                </div>
                <input
                  value={draft.name}
                  onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Prompt name"
                />
              </label>

              <label className="fieldGroup">
                <div className="fieldLabel">
                  <strong>Stage</strong>
                </div>
                <select
                  value={draft.stage}
                  onChange={(event) => setDraft((current) => ({ ...current, stage: event.target.value, content: current.id ? current.content : starterTemplate(event.target.value) }))}
                >
                  <option value="mcp_research">MCP research</option>
                  <option value="microsite_generation">Microsite generation</option>
                </select>
              </label>
            </div>

            <label className="fieldGroup">
              <div className="fieldLabel">
                <strong>Description</strong>
              </div>
              <input
                value={draft.description}
                onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
                placeholder="What makes this prompt useful?"
              />
            </label>

            <div className="promptPanel">
              <p className="miniLabel">Supported placeholders</p>
              <p>
                <code>{"{{company_name}}"}</code>, <code>{"{{mcp_context}}"}</code>, <code>{"{{mcp_context_block}}"}</code>
              </p>
            </div>

            <label className="fieldGroup">
              <div className="fieldLabel">
                <strong>Prompt content</strong>
                <span className="fieldHint">Template text sent to the backend pipeline</span>
              </div>
              <textarea
                className="promptTextarea"
                value={draft.content}
                onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))}
                placeholder="Write the prompt template here"
              />
            </label>

            <div className="stackActions">
              <button className="buttonPrimary" type="submit" disabled={saving || !draft.name.trim() || !draft.content.trim()}>
                {saving ? "Saving..." : draft.id ? "Save changes" : "Create prompt"}
              </button>
              <button className="buttonSecondary" onClick={handleActivate} type="button" disabled={saving || !draft.id || selectedPrompt?.is_active}>
                Activate for stage
              </button>
              <button className="buttonTertiary" onClick={handleDelete} type="button" disabled={saving || (selectedPrompt?.is_active ?? false)}>
                Delete
              </button>
            </div>
          </form>
        </section>
      </section>
    </main>
  );
}
