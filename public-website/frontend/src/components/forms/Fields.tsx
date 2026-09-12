/**
 * components/forms/Fields.tsx
 * ───────────────────────────
 * Form controls with accessibility wired in once.
 *
 * Every field here guarantees:
 *   - a real <label> bound to the control by id
 *   - hints and errors linked through aria-describedby
 *   - aria-invalid when there is an error
 *   - the error text rendered next to the field, not only at the top of a form
 *
 * That combination is what lets someone using a screen reader hear the label,
 * the requirement and the failure without hunting for them.
 */

import { useId } from 'react';
import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import { AlertIcon } from '@/components/common/Icons';

// ── Shared parts ────────────────────────────────────────────────────────────

interface FieldFrameProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  hintId: string;
  errorId: string;
  children: ReactNode;
  /** Rendered on the label row, e.g. a character counter. */
  labelAside?: ReactNode;
}

function FieldFrame({
  id,
  label,
  hint,
  error,
  required,
  hintId,
  errorId,
  children,
  labelAside,
}: FieldFrameProps) {
  return (
    <div className="field">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="label">
          {label}
          {required ? (
            <span className="ml-0.5 text-danger-600" aria-hidden="true">
              *
            </span>
          ) : (
            // ink-500 rather than ink-400: this marker says whether the field
            // has to be filled in, so it carries information and must meet the
            // 4.5:1 contrast minimum, not the relaxed bar for decoration.
            <span className="ml-1.5 text-xs font-normal text-ink-500">(optional)</span>
          )}
        </label>
        {labelAside}
      </div>

      {hint ? (
        <p id={hintId} className="hint">
          {hint}
        </p>
      ) : null}

      {children}

      {error ? (
        <p id={errorId} className="error-text">
          <AlertIcon className="mt-px h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}

function describedBy(hint: string | undefined, error: string | undefined, hintId: string, errorId: string) {
  return [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;
}

// ── Text input ──────────────────────────────────────────────────────────────

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  hint?: string;
  error?: string;
  labelAside?: ReactNode;
}

export function TextField({
  label,
  hint,
  error,
  required,
  className = '',
  labelAside,
  ...rest
}: TextFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  return (
    <FieldFrame
      id={id}
      label={label}
      hint={hint}
      error={error}
      required={required}
      hintId={hintId}
      errorId={errorId}
      labelAside={labelAside}
    >
      <input
        id={id}
        className={`input ${error ? 'input-invalid' : ''} ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, hintId, errorId)}
        aria-required={required || undefined}
        {...rest}
      />
    </FieldFrame>
  );
}

// ── Textarea ────────────────────────────────────────────────────────────────

export interface TextAreaFieldProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> {
  label: string;
  hint?: string;
  error?: string;
  /** Shows a live "x / y" counter and enforces the limit on the control. */
  maxChars?: number;
}

export function TextAreaField({
  label,
  hint,
  error,
  required,
  maxChars,
  value,
  className = '',
  ...rest
}: TextAreaFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const length = typeof value === 'string' ? value.length : 0;

  return (
    <FieldFrame
      id={id}
      label={label}
      hint={hint}
      error={error}
      required={required}
      hintId={hintId}
      errorId={errorId}
      labelAside={
        maxChars ? (
          <span
            className={`text-xs tabular-nums ${
              length > maxChars ? 'font-semibold text-danger-600' : 'text-ink-500'
            }`}
          >
            {length.toLocaleString()} / {maxChars.toLocaleString()}
          </span>
        ) : undefined
      }
    >
      <textarea
        id={id}
        value={value}
        maxLength={maxChars}
        className={`textarea ${error ? 'input-invalid' : ''} ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, hintId, errorId)}
        aria-required={required || undefined}
        {...rest}
      />
    </FieldFrame>
  );
}

// ── Select ──────────────────────────────────────────────────────────────────

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> {
  label: string;
  hint?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
}

export function SelectField({
  label,
  hint,
  error,
  required,
  options,
  placeholder,
  className = '',
  ...rest
}: SelectFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  return (
    <FieldFrame
      id={id}
      label={label}
      hint={hint}
      error={error}
      required={required}
      hintId={hintId}
      errorId={errorId}
    >
      <select
        id={id}
        className={`select ${error ? 'input-invalid' : ''} ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hint, error, hintId, errorId)}
        aria-required={required || undefined}
        {...rest}
      >
        {placeholder ? (
          <option value="" disabled>
            {placeholder}
          </option>
        ) : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldFrame>
  );
}

// ── Rating ──────────────────────────────────────────────────────────────────

export interface RatingFieldProps {
  label: string;
  value: number | null;
  onChange: (value: number) => void;
  error?: string;
  hint?: string;
  required?: boolean;
  disabled?: boolean;
}

/**
 * A radio group, not a row of clickable stars. Radios give keyboard support and
 * grouping semantics for free, and each option keeps a text label so the choice
 * never depends on interpreting an icon.
 */
export function RatingField({
  label,
  value,
  onChange,
  error,
  hint,
  required,
  disabled,
}: RatingFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  return (
    <fieldset
      className="field"
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy(hint, error, hintId, errorId)}
    >
      <legend className="label">
        {label}
        {required ? (
          <span className="ml-0.5 text-danger-600" aria-hidden="true">
            *
          </span>
        ) : null}
      </legend>

      {hint ? (
        <p id={hintId} className="hint">
          {hint}
        </p>
      ) : null}

      <div className="mt-1 flex flex-wrap gap-2">
        {[1, 2, 3, 4, 5].map((score) => {
          const optionId = `${id}-${score}`;
          const selected = value === score;
          return (
            <div key={score}>
              <input
                type="radio"
                id={optionId}
                name={id}
                value={score}
                checked={selected}
                onChange={() => onChange(score)}
                disabled={disabled}
                className="peer sr-only"
              />
              <label
                htmlFor={optionId}
                className={`flex h-11 min-w-[3.25rem] cursor-pointer items-center justify-center rounded-lg border px-3 text-sm font-semibold transition-colors
                  peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500 peer-focus-visible:ring-offset-2
                  ${
                    selected
                      ? 'border-brand-600 bg-brand-600 text-white'
                      : 'border-ink-200 bg-white text-ink-700 hover:bg-ink-50'
                  }`}
              >
                {score}
                <span className="sr-only"> out of 5</span>
              </label>
            </div>
          );
        })}
      </div>

      {error ? (
        <p id={errorId} className="error-text">
          <AlertIcon className="mt-px h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </p>
      ) : null}
    </fieldset>
  );
}

// ── Form-level error summary ────────────────────────────────────────────────

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="alert-danger" role="alert">
      <AlertIcon className="mt-0.5 h-5 w-5 shrink-0" />
      <p>{message}</p>
    </div>
  );
}
