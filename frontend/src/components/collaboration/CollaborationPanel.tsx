import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import SendRounded from '@mui/icons-material/SendRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { apiRequest } from '../../lib/api'
import type { AuthSession } from '../../lib/session'
import { parseTimestampInput } from './timestamp'

type ReviewStatus = 'draft' | 'in_review' | 'changes_requested' | 'approved'

type CollaborationPanelProps = {
  entityType: 'analysis_job' | 'analysis_comparison'
  entityId: string | null
  session: AuthSession
  title: string
  subtitle: string
  allowTimestampComments?: boolean
}

type WorkspaceMember = {
  id: string
  email: string
  full_name?: string | null
  role: string
}

type CollaborationComment = {
  id: string
  body: string
  timestamp_ms?: number | null
  segment_label?: string | null
  author?: WorkspaceMember | null
  created_at: string
}

type CollaborationReview = {
  id?: string | null
  entity_type: 'analysis_job' | 'analysis_comparison'
  entity_id: string
  status: ReviewStatus
  review_summary?: string | null
  created_by?: WorkspaceMember | null
  assignee?: WorkspaceMember | null
  approved_by?: WorkspaceMember | null
  approved_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  comments: CollaborationComment[]
}

const STATUS_LABELS: Record<ReviewStatus, string> = {
  draft: 'Draft',
  in_review: 'In review',
  changes_requested: 'Changes requested',
  approved: 'Approved',
}

function CollaborationPanel({
  entityType,
  entityId,
  session,
  title,
  subtitle,
  allowTimestampComments = false,
}: CollaborationPanelProps) {
  const sessionToken = session.sessionToken

  const [members, setMembers] = useState<WorkspaceMember[]>([])
  const [isLoadingMembers, setIsLoadingMembers] = useState(false)
  const [membersError, setMembersError] = useState<string | null>(null)

  const [review, setReview] = useState<CollaborationReview | null>(null)
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>('draft')
  const [assigneeUserId, setAssigneeUserId] = useState<string>('')
  const [reviewSummary, setReviewSummary] = useState('')
  const [isLoadingReview, setIsLoadingReview] = useState(false)
  const [reviewError, setReviewError] = useState<string | null>(null)

  const [commentBody, setCommentBody] = useState('')
  const [commentTimestamp, setCommentTimestamp] = useState('')
  const [commentSegmentLabel, setCommentSegmentLabel] = useState('')
  const [commentError, setCommentError] = useState<string | null>(null)

  const [isSaving, setIsSaving] = useState(false)
  const [isPostingComment, setIsPostingComment] = useState(false)

  const isMountedRef = useRef(true)
  const membersAbortRef = useRef<AbortController | null>(null)
  const reviewAbortRef = useRef<AbortController | null>(null)
  const lastMembersTokenRef = useRef<string | null>(null)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      membersAbortRef.current?.abort()
      reviewAbortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!sessionToken) {
      lastMembersTokenRef.current = null
      setMembers([])
      return
    }

    if (lastMembersTokenRef.current === sessionToken && members.length > 0) {
      return
    }

    membersAbortRef.current?.abort()
    const controller = new AbortController()
    membersAbortRef.current = controller

    setIsLoadingMembers(true)
    apiRequest<{ items: WorkspaceMember[] }>('/api/v1/analysis/collaboration/members', {
      sessionToken,
      signal: controller.signal,
    })
      .then((response) => {
        if (controller.signal.aborted || !isMountedRef.current) {
          return
        }
        setMembers(response.items)
        lastMembersTokenRef.current = sessionToken
        setMembersError(null)
      })
      .catch((error) => {
        if (controller.signal.aborted || !isMountedRef.current) {
          return
        }
        setMembersError(error instanceof Error ? error.message : 'Unable to load workspace members.')
      })
      .finally(() => {
        if (isMountedRef.current && !controller.signal.aborted) {
          setIsLoadingMembers(false)
        }
      })
  // We deliberately omit `members.length` to keep it triggering only on session changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionToken])

  useEffect(() => {
    if (!sessionToken || !entityId) {
      setReview(null)
      setReviewStatus('draft')
      setAssigneeUserId('')
      setReviewSummary('')
      return
    }

    reviewAbortRef.current?.abort()
    const controller = new AbortController()
    reviewAbortRef.current = controller

    setIsLoadingReview(true)
    apiRequest<CollaborationReview>(`/api/v1/analysis/collaboration/${entityType}/${entityId}`, {
      sessionToken,
      signal: controller.signal,
    })
      .then((response) => {
        if (controller.signal.aborted || !isMountedRef.current) {
          return
        }
        setReview(response)
        setReviewStatus(response.status)
        setAssigneeUserId(response.assignee?.id || '')
        setReviewSummary(response.review_summary || '')
        setReviewError(null)
      })
      .catch((error) => {
        if (controller.signal.aborted || !isMountedRef.current) {
          return
        }
        setReviewError(error instanceof Error ? error.message : 'Unable to load collaboration details.')
      })
      .finally(() => {
        if (isMountedRef.current && !controller.signal.aborted) {
          setIsLoadingReview(false)
        }
      })
  }, [entityId, entityType, sessionToken])

  const hasDraftChanges = useMemo(() => {
    return (
      reviewStatus !== (review?.status || 'draft') ||
      assigneeUserId !== (review?.assignee?.id || '') ||
      reviewSummary !== (review?.review_summary || '')
    )
  }, [assigneeUserId, review, reviewStatus, reviewSummary])

  const handleSaveReview = useCallback(async () => {
    if (!sessionToken || !entityId) {
      return
    }
    setIsSaving(true)
    try {
      const response = await apiRequest<CollaborationReview>(`/api/v1/analysis/collaboration/${entityType}/${entityId}`, {
        method: 'PUT',
        sessionToken,
        body: {
          status: reviewStatus,
          assignee_user_id: assigneeUserId || null,
          review_summary: reviewSummary.trim() || null,
        },
      })
      if (!isMountedRef.current) {
        return
      }
      setReview(response)
      setReviewStatus(response.status)
      setAssigneeUserId(response.assignee?.id || '')
      setReviewSummary(response.review_summary || '')
      setReviewError(null)
    } catch (error) {
      if (!isMountedRef.current) {
        return
      }
      setReviewError(error instanceof Error ? error.message : 'Unable to save review settings.')
    } finally {
      if (isMountedRef.current) {
        setIsSaving(false)
      }
    }
  }, [assigneeUserId, entityId, entityType, reviewStatus, reviewSummary, sessionToken])

  const validatedTimestamp = useMemo(() => parseTimestampInput(commentTimestamp), [commentTimestamp])
  const timestampInputError =
    allowTimestampComments && commentTimestamp.trim() !== '' && validatedTimestamp.kind === 'invalid'
      ? validatedTimestamp.reason
      : null

  const handleAddComment = useCallback(async () => {
    if (!sessionToken || !entityId) {
      return
    }
    const trimmedBody = commentBody.trim()
    if (!trimmedBody) {
      return
    }

    let timestampValue: number | null = null
    if (allowTimestampComments) {
      const timestampInput = parseTimestampInput(commentTimestamp)
      if (timestampInput.kind === 'invalid') {
        setCommentError(timestampInput.reason)
        return
      }
      timestampValue = timestampInput.value
    }

    setCommentError(null)
    setIsPostingComment(true)
    try {
      const response = await apiRequest<CollaborationReview>(
        `/api/v1/analysis/collaboration/${entityType}/${entityId}/comments`,
        {
          method: 'POST',
          sessionToken,
          body: {
            body: trimmedBody,
            timestamp_ms: timestampValue,
            segment_label: commentSegmentLabel.trim() || null,
          },
        },
      )
      if (!isMountedRef.current) {
        return
      }
      setReview(response)
      setCommentBody('')
      setCommentTimestamp('')
      setCommentSegmentLabel('')
    } catch (error) {
      if (!isMountedRef.current) {
        return
      }
      setCommentError(error instanceof Error ? error.message : 'Unable to add the comment.')
    } finally {
      if (isMountedRef.current) {
        setIsPostingComment(false)
      }
    }
  }, [
    allowTimestampComments,
    commentBody,
    commentSegmentLabel,
    commentTimestamp,
    entityId,
    entityType,
    sessionToken,
  ])

  if (!entityId) {
    return (
      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={1.25}>
          <Stack alignItems="center" direction="row" spacing={0.75}>
            <Typography variant="h6">{title}</Typography>
            <Tooltip arrow placement="top" title={subtitle}>
              <InfoOutlinedIcon
                aria-label={`${title} description`}
                fontSize="small"
                sx={{ color: 'text.secondary', cursor: 'help' }}
                tabIndex={0}
              />
            </Tooltip>
          </Stack>
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              Select an analysis or comparison to enable review and comments.
            </Typography>
          </Box>
        </Stack>
      </Paper>
    )
  }

  const isBusy = isLoadingMembers || isLoadingReview || isSaving || isPostingComment
  const visibleError = reviewError || membersError

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack
          alignItems={{ xs: 'stretch', sm: 'center' }}
          direction={{ xs: 'column', sm: 'row' }}
          justifyContent="space-between"
          spacing={1.5}
        >
          <Stack alignItems="center" direction="row" spacing={0.75}>
            <Typography variant="h6">{title}</Typography>
            <Tooltip arrow placement="top" title={subtitle}>
              <InfoOutlinedIcon
                aria-label={`${title} description`}
                fontSize="small"
                sx={{ color: 'text.secondary', cursor: 'help' }}
                tabIndex={0}
              />
            </Tooltip>
          </Stack>
          {review ? (
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={STATUS_LABELS[review.status]} size="small" variant="outlined" />
              {review.assignee ? (
                <Chip
                  label={`Assignee: ${review.assignee.full_name || review.assignee.email}`}
                  size="small"
                  variant="outlined"
                />
              ) : null}
            </Stack>
          ) : null}
        </Stack>

        {isBusy ? <LinearProgress sx={{ borderRadius: 999, height: 6 }} /> : null}
        {visibleError ? <Alert severity="warning">{visibleError}</Alert> : null}

        <Box className="dashboard-grid dashboard-grid--content">
          <Stack spacing={1.5}>
            <TextField
              label="Review status"
              onChange={(event) => setReviewStatus(event.target.value as ReviewStatus)}
              select
              value={reviewStatus}
            >
              {(Object.keys(STATUS_LABELS) as ReviewStatus[]).map((value) => (
                <MenuItem key={value} value={value}>
                  {STATUS_LABELS[value]}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              disabled={isLoadingMembers && members.length === 0}
              helperText={isLoadingMembers && members.length === 0 ? 'Loading members…' : undefined}
              label="Assignee"
              onChange={(event) => setAssigneeUserId(event.target.value)}
              select
              value={assigneeUserId}
            >
              <MenuItem value="">Unassigned</MenuItem>
              {members.map((member) => (
                <MenuItem key={member.id} value={member.id}>
                  {member.full_name || member.email} · {member.role}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              label="Review summary"
              minRows={3}
              multiline
              onChange={(event) => setReviewSummary(event.target.value)}
              value={reviewSummary}
            />

            <Button
              disabled={!hasDraftChanges || isSaving}
              onClick={() => void handleSaveReview()}
              variant="contained"
            >
              {isSaving ? 'Saving…' : 'Save review settings'}
            </Button>
          </Stack>

          <Stack spacing={1.5}>
            <Stack alignItems="center" direction="row" spacing={0.75}>
              <Typography variant="subtitle2">Add comment</Typography>
              <Tooltip
                arrow
                placement="top"
                title="Comments are visible to workspace members. Use timestamps for media-specific feedback."
              >
                <InfoOutlinedIcon
                  aria-label="Comment tips"
                  fontSize="small"
                  sx={{ color: 'text.secondary', cursor: 'help' }}
                  tabIndex={0}
                />
              </Tooltip>
            </Stack>
            <TextField
              label="Comment"
              minRows={3}
              multiline
              onChange={(event) => setCommentBody(event.target.value)}
              value={commentBody}
            />
            {allowTimestampComments ? (
              <TextField
                error={Boolean(timestampInputError)}
                helperText={timestampInputError ?? 'Optional. Position in milliseconds.'}
                inputProps={{ inputMode: 'numeric', min: 0 }}
                label="Timestamp (ms)"
                onChange={(event) => setCommentTimestamp(event.target.value)}
                type="number"
                value={commentTimestamp}
              />
            ) : null}
            <TextField
              label="Segment label (optional)"
              onChange={(event) => setCommentSegmentLabel(event.target.value)}
              value={commentSegmentLabel}
            />
            {commentError ? <Alert severity="error">{commentError}</Alert> : null}
            <Button
              disabled={!commentBody.trim() || isPostingComment || Boolean(timestampInputError)}
              onClick={() => void handleAddComment()}
              startIcon={<SendRounded />}
              variant="outlined"
            >
              {isPostingComment ? 'Posting…' : 'Post comment'}
            </Button>
          </Stack>
        </Box>

        <Box sx={{ maxHeight: 420, overflow: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Author</TableCell>
                <TableCell>Comment</TableCell>
                {allowTimestampComments ? <TableCell>Timestamp</TableCell> : null}
                <TableCell>Created</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(review?.comments || []).map((comment) => (
                <TableRow key={comment.id}>
                  <TableCell>{comment.author?.full_name || comment.author?.email || 'Workspace member'}</TableCell>
                  <TableCell>
                    <Stack spacing={0.5}>
                      <Typography variant="body2">{comment.body}</Typography>
                      {comment.segment_label ? (
                        <Typography color="text.secondary" variant="caption">
                          {comment.segment_label}
                        </Typography>
                      ) : null}
                    </Stack>
                  </TableCell>
                  {allowTimestampComments ? (
                    <TableCell>{comment.timestamp_ms != null ? `${comment.timestamp_ms} ms` : '—'}</TableCell>
                  ) : null}
                  <TableCell>{formatDateTime(comment.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>

        {review && review.comments.length === 0 ? (
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              No comments yet.
            </Typography>
          </Box>
        ) : null}
      </Stack>
    </Paper>
  )
}

function formatDateTime(value: string) {
  if (!value) {
    return '—'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export default memo(CollaborationPanel)
