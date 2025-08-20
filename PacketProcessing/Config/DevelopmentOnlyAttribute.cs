using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;


namespace PacketProcessing.Config;

public class DevelopmentOnlyAttribute : ActionFilterAttribute
{
    public override void OnActionExecuting(ActionExecutingContext context)
    {
        var env = context.HttpContext.RequestServices.GetService<IHostEnvironment>();
        if (env == null || !env.IsDevelopment())
        {
            context.Result = new NotFoundResult();
        }
    }  
}