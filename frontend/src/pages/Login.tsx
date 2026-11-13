import { LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";

import { BrandMark } from "../components/Layout";
import { Button, Callout, Card } from "../components/ui";
import { useAuth } from "../lib/auth";

export function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <div className="login__panel">
        <div className="brand" style={{ marginBottom: 18 }}>
          <BrandMark />
          <div>
            <div className="brand__name" style={{ color: "var(--ink)" }}>TenderShield</div>
            <div className="brand__tag" style={{ color: "var(--ink-3)" }}>Procurement restructuring</div>
          </div>
        </div>
        <Card title="Sign in">
          <form className="stack" onSubmit={submit}>
            <div className="field">
              <label htmlFor="login-email">Email</label>
              <input id="login-email" className="input" type="email" autoComplete="username" required autoFocus
                value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="login-password">Password</label>
              <input id="login-password" className="input" type="password" autoComplete="current-password" required
                value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <Button variant="brand" icon={<LogIn size={15} />} loading={busy}>Sign in</Button>
            {error && <Callout tone="danger">{error}</Callout>}
          </form>
        </Card>
        <p className="dim" style={{ fontSize: 12, marginTop: 12 }}>
          Accounts are issued by your administrator. Contact them if you need access or a password reset.
        </p>
      </div>
    </div>
  );
}
