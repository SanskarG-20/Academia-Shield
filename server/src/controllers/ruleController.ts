import { Request, Response } from 'express';
import Rule from '../models/Rule';

export const createRule = async (req: Request | any, res: Response) => {
  const { name, mode, websites, applications } = req.body;
  const rule = await Rule.create({
    name, mode, websites, applications, professorId: req.user.id
  });
  res.status(201).json(rule);
};

export const getRules = async (req: Request | any, res: Response) => {
  const rules = await Rule.find({ professorId: req.user.id });
  res.json(rules);
};