import React from "react";
import classes from "./select.module.css";

interface SelectProps {
  id?: string;
  name?: string;
  value?: string;
  label?: string;
  type?: string;
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  disabled?: boolean;
  children?: React.ReactNode;
  [key: string]: any;
}

const Select = ({
  id,
  name,
  value,
  label,
  type,
  onChange,
  disabled,
  children,
  ...rest
}: SelectProps) => {
  return (
    <div className={classes.inputWrapper}>
      <label htmlFor={name}>{label}</label>
      <select
        id={id}
        value={value}
        onChange={onChange}
        disabled={disabled}
        {...rest}
      >
        {children}
      </select>
    </div>
  );
};

export default Select;
