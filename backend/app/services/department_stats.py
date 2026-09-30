"""Department aggregation shared by leave and trip analytics."""

from collections import Counter


def build_department_comparison(employees, departments, dept_days, metric):
    headcounts = Counter(emp.dept_id for emp in employees)
    department_map = {dept.dept_id: dept for dept in departments}
    employee_names = {emp.dept_id: emp.dept_name or "未分配" for emp in employees}

    def label(dept_id):
        names = []
        seen = set()
        current = dept_id
        while current in department_map and current not in seen:
            seen.add(current)
            dept = department_map[current]
            names.append(dept.name)
            current = dept.parent_id
        return " / ".join(reversed(names)) or employee_names[dept_id]

    labels = {dept_id: label(dept_id) for dept_id in headcounts}
    duplicate_labels = Counter(labels.values())
    rows = []
    raw_values = []
    for dept_id, headcount in headcounts.items():
        total_days = dept_days.get(dept_id, 0.0)
        avg_days = total_days / headcount
        name = labels[dept_id]
        if duplicate_labels[name] > 1:
            name = f"{name} [{dept_id}]"
        rows.append({
            "name": name,
            "totalDays": round(total_days, 1),
            "avgDays": round(avg_days, 1),
            "headcount": headcount,
        })
        raw_values.append(avg_days if metric == "avg" else total_days)

    sort_key = "avgDays" if metric == "avg" else "totalDays"
    rows.sort(key=lambda row: row[sort_key], reverse=True)
    average = sum(raw_values) / len(raw_values) if raw_values else 0.0
    return {"departments": rows, "average": round(average, 1)}
