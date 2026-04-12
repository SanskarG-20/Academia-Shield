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

export const deleteRule = async (req: Request | any, res: Response) => {
  const rule = await Rule.findById(req.params.id);

  if (!rule) {
    return res.status(404).json({ message: 'Rule not found' });
  }

  if (rule.professorId.toString() !== req.user.id) {
    return res.status(403).json({ message: 'Not authorised to delete this rule' });
  }

  await rule.deleteOne();
  res.json({ success: true });
};