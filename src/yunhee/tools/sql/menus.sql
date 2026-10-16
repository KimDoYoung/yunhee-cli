WITH RECURSIVE t AS (
  SELECT sys06_menu_id id, sys06_menu_nm::text path, sys06_seq::text sort FROM sys06_menu WHERE sys06_parent_id = 0
  UNION ALL
  SELECT m.sys06_menu_id, t.path || ' > ' || m.sys06_menu_nm, t.sort || '.' || coalesce(m.sys06_seq,'')
  FROM sys06_menu m JOIN t ON m.sys06_parent_id = t.id
)
SELECT coalesce(m.sys06_menu_no,'') AS menu_no,
       t.path AS menu_path,
       m.sys06_class_nm AS class_nm,
       coalesce(m.sys06_use_yn,'') AS use_yn
FROM t JOIN sys06_menu m ON m.sys06_menu_id = t.id
WHERE coalesce(m.sys06_class_nm,'') <> ''
ORDER BY t.sort
