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
  ...rest
}) => {
  return (
    <div className={classes.inputWrapper}>
      <label htmlFor={name}>{label}</label>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          onChange={onChange}
          disabled={disabled}
          {...rest}
        ></textarea>
      ) : (
        <input
          type={type}
          id={id}
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
