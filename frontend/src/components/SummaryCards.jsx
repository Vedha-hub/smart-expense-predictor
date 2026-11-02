const inr = (n) => "₹" + Math.round(n).toLocaleString("en-IN");

export default function SummaryCards({ summary, predicted, horizon }) {
  const cards = [
    ["Total spent", inr(summary.total_spent)],
    ["Transactions", summary.transactions],
    ["Avg / day", inr(summary.avg_per_day)],
    [`Predicted next ${horizon} days`, inr(predicted)],
  ];
  return (
    <div className="cards">
      {cards.map(([label, value]) => (
        <div className="card" key={label}>
          <div className="muted">{label}</div>
          <div className="big">{value}</div>
        </div>
      ))}
    </div>
  );
}
