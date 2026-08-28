"use client";

import { useEffect, useRef, useState } from "react";
import { createDept, getDepts, renameDept } from "@/services/admin";
import { Dept } from "@/types/dept";
import { Badge, Button, EmptyState, Field, Panel, Table } from "@/components/ui";
import styles from "./page.module.css";

export default function DeptsPage() {
  const [depts, setDepts] = useState<Dept[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [renaming, setRenaming] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    load();
  }, []);

  // 편집 모드로 들어갈 때 입력에 포커스를 옮긴다. 마우스로 시작했든 키보드로
  // 시작했든(수정 버튼을 Enter/Space 로 눌렀든) 이름 입력이 즉시 조작 가능해야
  // 한다.
  useEffect(() => {
    if (editingId !== null) {
      editInputRef.current?.focus();
    }
  }, [editingId]);

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      setDepts(await getDepts());
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "부서 목록을 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);
    if (!newName.trim()) return;

    setAdding(true);
    try {
      await createDept(newName.trim());
      setNewName("");
      setSuccessMessage("부서를 추가했습니다.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "부서 추가에 실패했습니다");
    } finally {
      setAdding(false);
    }
  }

  function startEdit(dept: Dept) {
    setError(null);
    setSuccessMessage(null);
    setEditingId(dept.id);
    setEditingName(dept.dept);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditingName("");
  }

  async function handleRename(id: number) {
    setError(null);
    setSuccessMessage(null);
    if (!editingName.trim()) return;

    setRenaming(true);
    try {
      await renameDept(id, editingName.trim());
      setEditingId(null);
      setSuccessMessage("부서명을 변경했습니다.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "부서명 변경에 실패했습니다");
    } finally {
      setRenaming(false);
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.wrapper}>
        <Panel title="부서 추가">
          <form className={styles.addForm} onSubmit={handleAdd}>
            <div className={styles.addFormField}>
              <Field label="새 부서명" htmlFor="new-dept-name">
                <input
                  id="new-dept-name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="내과"
                />
              </Field>
            </div>
            <Button type="submit" variant="primary" disabled={adding} loading={adding}>
              추가
            </Button>
          </form>
        </Panel>

        {error && (
          <div className={styles.errorMessage} role="alert">
            {error}
          </div>
        )}
        {successMessage && (
          <div className={styles.successMessage} role="status">
            {successMessage}
          </div>
        )}

        <Panel title="부서 목록" padding="none">
          {loading ? (
            <EmptyState title="로딩 중..." />
          ) : loadError ? (
            <EmptyState
              title="부서 목록을 불러오지 못했습니다"
              description={loadError}
              action={
                <Button variant="secondary" size="sm" onClick={load}>
                  다시 시도
                </Button>
              }
            />
          ) : depts.length === 0 ? (
            <EmptyState title="등록된 부서가 없습니다" />
          ) : (
            <Table aria-label="부서 목록">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">부서명</th>
                  <th scope="col">소속 인원</th>
                  <th scope="col"></th>
                </tr>
              </thead>
              <tbody>
                {depts.map((d) => (
                  <tr key={d.id}>
                    <td>{d.id}</td>
                    <td className={styles.deptCell}>
                      {editingId === d.id ? (
                        <input
                          ref={editInputRef}
                          value={editingName}
                          onChange={(e) => setEditingName(e.target.value)}
                          aria-label={`${d.dept} 이름 수정`}
                        />
                      ) : (
                        d.dept
                      )}
                    </td>
                    <td>
                      <Badge tone="neutral">{d.employeeCount}</Badge>
                    </td>
                    <td className={styles.editCell}>
                      {editingId === d.id ? (
                        <div className={styles.editActions}>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleRename(d.id)}
                            disabled={renaming}
                            loading={renaming}
                          >
                            저장
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={cancelEdit}
                            disabled={renaming}
                          >
                            취소
                          </Button>
                        </div>
                      ) : (
                        <Button variant="secondary" size="sm" onClick={() => startEdit(d)}>
                          이름 수정
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>
    </div>
  );
}
