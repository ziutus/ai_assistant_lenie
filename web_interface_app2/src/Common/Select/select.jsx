import React from "react";
import classes from "./select.module.css";

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
}) => {
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
