/**
 * Small display helpers shared across the exception views. All real figures
 * and AI text come from the backend (`api.getExceptionDetail`); nothing here
 * fabricates a value.
 */

import { EXCEPTION_LABELS } from "./api";
import type { Transaction } from "./types";

export function exceptionTypeLabel(t: Transaction) {
  return t.exceptionType ? EXCEPTION_LABELS[t.exceptionType] : "Matched";
}
