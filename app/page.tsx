"use client";

import { FormEvent, useEffect, useState } from "react";

type BackendHealth = {
  status: string;
};

type BackendHello = {
  message: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  const [name, setName] = useState("Gautham");
  const [health, setHealth] = useState("Checking backend...");
  const [message, setMessage] = useState("Waiting for backend response...");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function checkHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/health`);
        if (!response.ok) {
          throw new Error(`Health check failed with ${response.status}`);
        }

        const data: BackendHealth = await response.json();
        setHealth(data.status);
      } catch {
        setHealth("Backend unavailable");
      }
    }

    void checkHealth();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch(
        `${apiBaseUrl}/api/hello?name=${encodeURIComponent(name.trim() || "World")}`,
      );

      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`);
      }

      const data: BackendHello = await response.json();
      setMessage(data.message);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to reach backend");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <section className="card">
        <p className="eyebrow">Starter</p>
        <h1>Next.js frontend + FastAPI backend</h1>
        <p className="description">
          This is a fresh starter. The frontend calls the FastAPI backend directly and shows the returned
          message below.
        </p>

        <div className="statusRow">
          <div className="statusCard">
            <span className="statusLabel">Backend URL</span>
            <strong>{apiBaseUrl}</strong>
          </div>
          <div className="statusCard">
            <span className="statusLabel">Health</span>
            <strong>{health}</strong>
          </div>
        </div>

        <form className="form" onSubmit={handleSubmit}>
          <label className="field" htmlFor="name">
            <span>Name</span>
            <input
              id="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Enter a name"
            />
          </label>

          <button className="button" type="submit" disabled={loading}>
            {loading ? "Calling backend..." : "Send request"}
          </button>
        </form>

        <div className="responseBox">
          <span className="statusLabel">Response</span>
          <p>{message}</p>
          {error ? <p className="errorText">{error}</p> : null}
        </div>
      </section>
    </main>
  );
}
