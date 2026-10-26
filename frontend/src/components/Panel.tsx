import type { ReactNode } from "react";
import type { State } from "../api";

interface Props<T> {
  title: string;
  subtitle?: string;
  state: State<T>;
  isEmpty?: (d: T) => boolean;
  emptyText?: string;
  children: (d: T) => ReactNode;
  wide?: boolean;
}

/** Every data section goes through here so loading / error+retry / empty states are consistent. */
export function Panel<T>({ title, subtitle, state, isEmpty, emptyText = "No data to show.", children, wide }: Props<T>) {
  const { data, error, loading, reload } = state;
  let body: ReactNode;
  if (loading && !data) body = <div className="status" role="status" aria-live="polite"><span className="spinner" aria-hidden="true" /> Loading {title.toLowerCase()}…</div>;
  else if (error) body = (
    <div className="status error" role="alert">
      <p>Could not load {title.toLowerCase()}: {error}</p>
      <button onClick={reload}>Retry</button>
    </div>
  );
  else if (!data || (isEmpty && isEmpty(data))) body = <div className="status empty">{emptyText}</div>;
  else body = children(data);
  return (
    <section className={`panel${wide ? " wide" : ""}`} aria-label={title}>
      <header><h2>{title}</h2>{subtitle && <p className="sub">{subtitle}</p>}</header>
      {body}
    </section>
  );
}
