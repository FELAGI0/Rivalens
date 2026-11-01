"use client";

import type { InputHTMLAttributes } from "react";

/** 1px border input; focus = 2px accent outline, never a box-shadow. */
export function Input({
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`w-full rounded-sm border border-line bg-bg px-3 py-2 text-sm text-fg placeholder:text-fg-faint outline-none focus:outline focus:outline-2 focus:outline-accent transition-colors duration-150 ${className}`}
      {...rest}
    />
  );
}
