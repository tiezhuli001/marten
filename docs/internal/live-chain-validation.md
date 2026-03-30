# Live Chain Validation

## Overview

This document describes the validation strategy for live chain operations.

## Validation Rules

1. Chain integrity must be verified before any write operations
2. State consistency checks should run on every block import
3. Finalization requires proof of checkpoint signatures

## Monitoring

- Track chain tip changes
- Alert on reorgs deeper than finalization threshold
- Monitor block production latency

<!-- sleep-coding-marker: 20260325T092406Z -->