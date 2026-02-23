import React from "react";
import classes from "./input.module.css";

interface InputProps {
  id?: string;
  name?: string;
  value?: string;
  label?: string;
  type?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void;
  disabled?: boolean;
  multiline?: boolean;
  children?: React.ReactNode;
  className?: string;
  required?: boolean;
  [key: string]: any;
}

const Input = ({
                 id,
                 name,
                 value,
                 label,
                 type,
                 onChange,
                 disabled,
                 multiline,
                 children,
                 className,
                 ...rest
               }: InputProps) => {
  return (
      <div className={classes.inputWrapper}>
        <label htmlFor={name}>{label}</label>
        {type === 'select' ? (
            <select
                id={id}
                name={name}
                value={value}
                onChange={onChange}
                disabled={disabled}
                className={`${classes.selectField} ${className}`}
                {...rest}
            >
              {children}
            </select>
        ) : multiline ? (
            <textarea
                id={id}
                name={name}
                value={value}
                onChange={onChange}
                disabled={disabled}
                {...rest}
            ></textarea>
        ) : (
            <input
                type={type}
                id={id}
                name={name}
                value={value}
                onChange={onChange}
                disabled={disabled}
                {...rest}
            />
        )}
      </div>
  );
};

export default Input;
