import { Response } from 'express';

export type ApiSuccess<T> = {
  success: true;
  data: T;
  message: string;
};

export type ApiFailure = {
  success: false;
  data: null;
  message: string;
};

export const sendSuccess = <T>(
  res: Response,
  data: T,
  message = 'OK',
  statusCode = 200
) => {
  const payload: ApiSuccess<T> = {
    success: true,
    data,
    message,
  };

  return res.status(statusCode).json(payload);
};

export const sendError = (
  res: Response,
  message: string,
  statusCode = 400
) => {
  const payload: ApiFailure = {
    success: false,
    data: null,
    message,
  };

  return res.status(statusCode).json(payload);
};