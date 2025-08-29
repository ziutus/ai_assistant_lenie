import React from "react";
import classes from "./input.module.css";

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
               }) => {
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
